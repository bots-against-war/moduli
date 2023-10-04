import base64
import datetime
import logging
from typing import Optional, Union

import cachetools  # type: ignore
from telebot import AsyncTeleBot
from telebot import api as tg_api
from telebot import types as tg
from telebot.types import constants as tg_const
from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.stores.generic import KeyFlagStore, KeySetStore

from telebot_constructor.app_models import TgGroupChat, TgGroupChatType
from telebot_constructor.utils import non_capturing_handler
from telebot_constructor.utils.rate_limit_retry import rate_limit_retry

logger = logging.getLogger(__name__)


class GroupChatDiscoveryHandler:
    """
    Service class that encapsulates group chat discovery functionality for bots
    (e.g. to automagically discover admin chats for users)
    """

    STORE_PREFIX = "telebot-constructor-group-chat-discovery"

    def __init__(self, redis: RedisInterface) -> None:
        # "{username}-{bot name}" -> flag for group chat discovery mode
        self._bots_in_discovery_mode_store = KeyFlagStore(
            name="bot-in-discovery-mode",
            prefix=self.STORE_PREFIX,
            redis=redis,
            expiration_time=datetime.timedelta(days=10),
        )
        # "{username}-{bot name}" -> set of discovered group chat ids
        self._available_group_chat_ids = KeySetStore[Union[str, int]](
            name="available-group-chat-ids",
            prefix=self.STORE_PREFIX,
            redis=redis,
            expiration_time=None,
            dumper=str,
            loader=int,
        )
        # file_id -> base64-encoded photo cache for telegram chat avatars
        self.chat_photo_cache = cachetools.LRUCache[str, str](maxsize=128)

    def _full_key(self, username: str, bot_name: str) -> str:
        return f"{username}-{bot_name}"

    async def start_discovery(self, username: str, bot_name: str) -> None:
        await self._bots_in_discovery_mode_store.set_flag(self._full_key(username, bot_name))

    async def stop_discovery(self, username: str, bot_name: str) -> None:
        await self._bots_in_discovery_mode_store.unset_flag(self._full_key(username, bot_name))

    async def is_discovering(self, username: str, bot_name: str) -> bool:
        return await self._bots_in_discovery_mode_store.is_flag_set(self._full_key(username, bot_name))

    async def save_discovered_chat(self, username: str, bot_name: str, chat_id: Union[str, int]) -> None:
        await self._available_group_chat_ids.add(self._full_key(username, bot_name), chat_id)

    async def get_group_chat(self, bot: AsyncTeleBot, chat_id: Union[int, str]) -> Optional[TgGroupChat]:
        prefix = f"{bot.log_marker} (getting info for chat {chat_id}) "
        try:
            async for attempt in rate_limit_retry():
                with attempt:
                    raw_chat = await bot.get_chat(chat_id)
        except tg_api.ApiException:
            logger.info(prefix + "Error, assuming chat does not exist / is not available to bot", exc_info=True)
            return None
        photo_b64: Optional[str] = None
        if raw_chat.photo is not None:
            chat_photo_file_id = raw_chat.photo.small_file_id  # small file = 160x160 preview
            photo_b64 = self.chat_photo_cache.get(chat_photo_file_id)
            if photo_b64 is not None:
                logger.info(prefix + "Chat photo loaded from cache")
            else:
                logger.info(prefix + "Chat photo not in cache, downloading")
                try:
                    file = await bot.get_file(chat_photo_file_id)
                    photo_bytes = await bot.download_file(file_path=file.file_path)
                    photo_b64 = base64.b64encode(photo_bytes).decode("utf-8")
                    self.chat_photo_cache[chat_photo_file_id] = photo_b64
                    logger.info(prefix + f"Chat photo loaded and saved in cache (size {len(photo_b64) / 1024} KiB)")
                except Exception:
                    logger.info("Error downloading chat avatar photo, ignoring it", exc_info=True)
        return TgGroupChat(
            id=raw_chat.id,
            type=TgGroupChatType(raw_chat.type),
            title=raw_chat.title or "",
            description=raw_chat.description,
            username=raw_chat.username,
            is_forum=raw_chat.is_forum,
            photo=photo_b64,
        )

    async def validate_discovered_chats(self, username: str, bot_name: str, bot: AsyncTeleBot) -> list[TgGroupChat]:
        """
        Check saved available chats and validate they are still available to the bot (i.e. it was not kicked, group chat
        was not promoted to supergroup, etc); return a list of valid chats as telegram Chat objects
        """
        prefix = f"{bot_name!r} by {username!r} (validating discovered chats)"
        chats: list[TgGroupChat] = []
        key = self._full_key(username, bot_name)
        available_chat_ids = await self._available_group_chat_ids.all(key)
        logger.info(prefix + f"Available chat ids: {sorted(available_chat_ids)}")
        for chat_id in available_chat_ids:
            chat = await self.get_group_chat(bot, chat_id=chat_id)
            if chat is None:
                logger.info(prefix + f"No chat retrieved for id {chat_id}, removing it from available list")
                await self._available_group_chat_ids.remove(key, chat_id)
            else:
                chats.append(chat)
        return chats

    def setup_handlers(self, username: str, bot_name: str, bot: AsyncTeleBot) -> None:
        @bot.my_chat_member_handler()
        @non_capturing_handler
        async def discover_group_chats_on_add(cmu: tg.ChatMemberUpdated) -> None:
            if (
                tg_const.ChatType(cmu.chat.type) is not tg_const.ChatType.private
                and cmu.new_chat_member.status in {"creator", "administrator", "member", "restricted"}
                and await self.is_discovering(username, bot_name)
            ):
                logger.info(f"Discovered chat from being added: {cmu.chat.id}")
                await self.save_discovered_chat(username, bot_name, chat_id=cmu.chat.id)
            if cmu.new_chat_member.status in {"kicked", "left"}:
                logger.info(f"Undiscovered chat from being kicked: {cmu.chat.id}")
                await self._available_group_chat_ids.remove(self._full_key(username, bot_name), cmu.chat.id)

        @bot.message_handler(commands=["discover_chat"])
        @non_capturing_handler
        async def discover_group_chat_on_explicit_cmd(message: tg.Message) -> None:
            if tg_const.ChatType(message.chat.type) is not tg_const.ChatType.private and await self.is_discovering(
                username, bot_name
            ):
                logger.info(f"Discovered chat from explicit command: {message.chat.id}")
                await self.save_discovered_chat(username, bot_name, chat_id=message.chat.id)

        @bot.message_handler(commands=["undiscover_chat"])
        @non_capturing_handler
        async def undiscover_group_chat(message: tg.Message) -> None:
            logger.info(f"Undiscovered chat from explicit command: {message.chat.id}")
            await self._available_group_chat_ids.remove(self._full_key(username, bot_name), message.chat.id)

        @bot.message_handler(
            content_types=[
                tg_const.ServiceContentType.migrate_to_chat_id,
                tg_const.ServiceContentType.migrate_from_chat_id,
            ]
        )
        @non_capturing_handler
        async def catch_group_to_supergroup_migration(message: tg.Message) -> None:
            if message.migrate_from_chat_id is not None:
                logger.info(f"Migrate from chat {message.migrate_from_chat_id} message detected, undiscovering")
                await self._available_group_chat_ids.remove(
                    self._full_key(username, bot_name),
                    message.migrate_from_chat_id,
                )
            if message.migrate_to_chat_id is not None:
                logger.info(
                    f"Migrate to chat {message.migrate_to_chat_id} message detected, undiscovering current chat"
                )
                await self._available_group_chat_ids.remove(
                    self._full_key(username, bot_name),
                    message.chat.id,
                )