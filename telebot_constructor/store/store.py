import itertools
import logging
import time
from typing import AsyncGenerator, Optional

from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.stores.generic import (
    KeyDictStore,
    KeyListStore,
    KeyVersionedValueStore,
    SetStore,
)

from telebot_constructor.app_models import BotInfo, BotVersionInfo
from telebot_constructor.bot_config import BotConfig
from telebot_constructor.constants import CONSTRUCTOR_PREFIX
from telebot_constructor.store.errors import BotErrorsStore
from telebot_constructor.store.form_results import FormResultsStore
from telebot_constructor.store.types import (
    BotConfigVersionMetadata,
    BotEvent,
    BotVersion,
)
from telebot_constructor.utils import log_prefix

logger = logging.getLogger(__name__)


def set_current_timestamp(data: BotConfigVersionMetadata | BotEvent):
    if "timestamp" not in data:
        data["timestamp"] = time.time()


class Store:
    """Main Redis-based application storage class"""

    def __init__(self, redis: RedisInterface) -> None:
        # owner id + bot id composite key -> versioned bot config
        self._config_store = KeyVersionedValueStore[BotConfig, BotConfigVersionMetadata](
            name="config",
            prefix=CONSTRUCTOR_PREFIX,
            redis=redis,
            snapshot_dumper=lambda config: config.model_dump(mode="json"),
            snapshot_loader=BotConfig.model_validate,
        )

        # owner id -> bot id -> currently running version
        # the version here is either:
        # - a number corresponding to a bot config version
        # - "stub" for a stub bot (e.g. for chat discovery)
        self._running_version_store = KeyDictStore[BotVersion](
            name="running-version",
            prefix=CONSTRUCTOR_PREFIX,
            redis=redis,
            expiration_time=None,
        )

        # owner id + bot id composite key -> list of events that happened to bot
        self._bot_events_store = KeyListStore[BotEvent](
            name="bot-events",
            prefix=CONSTRUCTOR_PREFIX,
            redis=redis,
        )

        # owner id -> bot id -> bot display name
        self._display_names_store = KeyDictStore[str](
            name="display-name",
            prefix=CONSTRUCTOR_PREFIX,
            redis=redis,
            expiration_time=None,
            dumper=str,
            loader=str,
        )
        self._hashed_tokens_store = SetStore(
            name="hashed-tokens",
            prefix=CONSTRUCTOR_PREFIX,
            redis=redis,
            expiration_time=None,
            dumper=str,
            loader=str,
        )

        self.form_results = FormResultsStore(redis=redis)
        self.errors = BotErrorsStore(redis=redis)

    # bot config store CRUD

    def _composite_key(self, owner_id: str, bot_id: str) -> str:
        return f"{owner_id}/{bot_id}"

    async def load_bot_config(self, owner_id: str, bot_id: str, version: BotVersion = -1) -> BotConfig | None:
        load_version = version if version != "stub" else -1
        if res := await self._config_store.load_version(
            self._composite_key(owner_id, bot_id),
            version=load_version,
        ):
            config, _version_meta = res
            if version == "stub":
                return config.stub()
            else:
                return config
        else:
            return None

    async def save_bot_config(
        self,
        owner_id: str,
        bot_id: str,
        config: BotConfig,
        meta: BotConfigVersionMetadata,
    ) -> bool:
        set_current_timestamp(meta)
        return await self._config_store.save(self._composite_key(owner_id, bot_id), config, meta)

    async def remove_bot_config(self, owner_id: str, bot_id: str) -> bool:
        return await self._config_store.drop(self._composite_key(owner_id, bot_id))

    async def bot_config_version_count(self, owner_id: str, bot_id: str) -> int:
        return await self._config_store.count_versions(self._composite_key(owner_id, bot_id))

    async def is_bot_exists(self, owner_id: str, bot_id: str) -> bool:
        return await self.bot_config_version_count(owner_id, bot_id) > 0

    async def list_bot_ids(self, owner_id: str) -> list[str]:
        keys = await self._config_store.find_keys(pattern=self._composite_key(owner_id, "*"))
        prefix = self._composite_key(owner_id, "")
        return [k.removeprefix(prefix) for k in keys]

    # running status methods

    async def is_bot_running(self, owner_id: str, bot_id: str) -> bool:
        return await self._running_version_store.get_subkey(owner_id, bot_id) is not None

    async def set_bot_not_running(self, owner_id: str, bot_id: str) -> bool:
        return await self._running_version_store.remove_subkey(owner_id, bot_id)

    async def set_bot_running_version(self, owner_id: str, bot_id: str, version: BotVersion) -> bool:
        return await self._running_version_store.set_subkey(owner_id, bot_id, version)

    async def get_bot_running_version(self, owner_id: str, bot_id: str) -> BotVersion | None:
        return await self._running_version_store.get_subkey(owner_id, bot_id)

    async def iter_running_bot_versions(self) -> AsyncGenerator[tuple[str, str, BotVersion], None]:
        owner_ids = await self._running_version_store.list_keys()
        for owner_id in owner_ids:
            bot_versions = await self._running_version_store.load(owner_id)
            for bot_id, version in bot_versions.items():
                yield owner_id, bot_id, version

    # bot event log methods

    async def save_event(self, owner_id: str, bot_id: str, event: BotEvent) -> bool:
        set_current_timestamp(event)
        return await self._bot_events_store.push(self._composite_key(owner_id, bot_id), event) == 1

    async def save_bot_display_name(self, owner_id: str, bot_id: str, display_name: str) -> bool:
        return await self._display_names_store.set_subkey(owner_id, bot_id, display_name)

    async def load_bot_display_name(self, owner_id: str, bot_id: str) -> Optional[str]:
        return await self._display_names_store.get_subkey(owner_id, bot_id)

    async def load_bot_info(self, owner_id: str, bot_id: str, detailed: bool) -> Optional[BotInfo]:
        INCLUDE_LAST_EVENTS = 5 if detailed else 1
        INCLUDE_LAST_VERSIONS = 1
        INCLUDE_LAST_ERRORS = 3

        running_version = await self.get_bot_running_version(owner_id, bot_id)
        if running_version == "stub":
            running_version = None

        running_version_info: BotVersionInfo | None = None
        if running_version is not None:
            running_version_info_list = await self.load_version_info(
                owner_id=owner_id,
                bot_id=bot_id,
                start_version=running_version,
                end_version=running_version,
            )
            if len(running_version_info_list) == 1:
                running_version_info = running_version_info_list[0]
            else:
                logger.error(
                    f"{log_prefix(owner_id, bot_id)} Error loading running version info: "
                    + f"{len(running_version_info_list)=}"
                )

        version_count = await self.bot_config_version_count(owner_id, bot_id)
        if version_count == 0:
            return None
        min_version = max(version_count - INCLUDE_LAST_VERSIONS, 0)
        last_versions = await self.load_version_info(
            owner_id,
            bot_id,
            start_version=min_version,
            end_version=None,
        )

        admin_chat_ids: list[str | int] = []
        if detailed and (config := await self.load_bot_config(owner_id, bot_id, version=running_version or -1)):
            for b in config.user_flow_config.blocks:
                if b.human_operator is not None and b.human_operator.feedback_handler_config.admin_chat_id is not None:
                    admin_chat_ids.append(b.human_operator.feedback_handler_config.admin_chat_id)
                if (
                    b.form is not None
                    and b.form.results_export.to_chat is not None
                    and not b.form.results_export.to_chat.via_feedback_handler
                    and b.form.results_export.to_chat.chat_id is not None
                ):
                    admin_chat_ids.append(b.form.results_export.to_chat.chat_id)

        return BotInfo(
            bot_id=bot_id,
            display_name=await self.load_bot_display_name(owner_id, bot_id) or bot_id,
            running_version=running_version,
            running_version_info=running_version_info,
            last_versions=last_versions,
            last_events=(
                await self._bot_events_store.tail(key=self._composite_key(owner_id, bot_id), start=-INCLUDE_LAST_EVENTS)
                or []
            ),
            forms_with_responses=(await self.form_results.list_forms(owner_id, bot_id) if detailed else []),
            last_errors=(
                await self.errors.load_errors(owner_id, bot_id, offset=0, count=INCLUDE_LAST_ERRORS) if detailed else []
            ),
            admin_chat_ids=admin_chat_ids,
            alert_chat_id=await self.errors.load_alert_chat_id(owner_id, bot_id),
        )

    async def load_version_info(
        self, owner_id: str, bot_id: str, start_version: int, end_version: int | None
    ) -> list[BotVersionInfo]:
        if start_version < 0 or (end_version is not None and end_version < 0):
            total = await self.bot_config_version_count(owner_id, bot_id)
            if start_version < 0:
                start_version = max(total + start_version, 0)
            if end_version is not None and end_version < 0:
                end_version = total + end_version
                if end_version < 0:
                    return []
        logger.info(f"Loading version info from {start_version} to {end_version}")
        key = self._composite_key(owner_id, bot_id)
        raw_versions = (
            await self._config_store.load_raw_versions(key, start_version=start_version)
            if end_version is None
            else (await self._config_store._version_store.slice(key, start=start_version, end=end_version) or [])
        )
        version_metadata = [v.meta for v in raw_versions if v.meta is not None]
        if len(version_metadata) != len(raw_versions):
            logger.error(
                f"[{owner_id}][{bot_id}] Version metadata list has unexpected length: "
                + f"{len(version_metadata) = }, {len(raw_versions) = }"
            )
        return [
            BotVersionInfo(
                version=version,
                metadata=metadata,
            )
            for version, metadata in zip(itertools.count(start_version), version_metadata)
        ]

    async def load_owner_id(self, actor_id: str, bot_id: str) -> str | None:
        if await self.is_bot_exists(actor_id, bot_id):
            return actor_id  # the actor owns the bot, they're the boss

        return None

    async def save_used_token_hash(self, hash: str) -> None:
        await self._hashed_tokens_store.add(hash)

    async def remove_used_token_hash(self, hash: str) -> None:
        await self._hashed_tokens_store.remove(hash)

    async def is_token_hash_saved(self, hash: str) -> bool:
        return await self._hashed_tokens_store.includes(hash)
