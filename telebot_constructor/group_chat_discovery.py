import datetime
import logging
from typing import Optional

from telebot import AsyncTeleBot
from telebot import api as tg_api
from telebot import types as tg
from telebot.types import constants as tg_const
from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.stores.generic import KeyFlagStore, KeySetStore

from telebot_constructor.app_models import TgGroupChat, TgGroupChatType
from telebot_constructor.constants import CONSTRUCTOR_PREFIX
from telebot_constructor.telegram_files_downloader import TelegramFilesDownloader
from telebot_constructor.utils import (
    AnyChatId,
    non_capturing_handler,
    parse_any_chat_id,
)
from telebot_constructor.utils.rate_limit_retry import rate_limit_retry

logger = logging.getLogger(__name__)


class GroupChatDiscoveryHandler:
    """
    Service class that encapsulates group chat discovery functionality for bots
    (e.g. to automagically discover admin chats for users)
    """

    STORE_PREFIX = f"{CONSTRUCTOR_PREFIX}/group-chat-discovery"

    def __init__(self, redis: RedisInterface, telegram_files_downloader: TelegramFilesDownloader) -> None:
        # "{username}-{bot name}" -> flag for group chat discovery mode
        self._bots_in_discovery_mode_store = KeyFlagStore(
            name="bot-in-discovery-mode",
            prefix=self.STORE_PREFIX,
            redis=redis,
            expiration_time=datetime.timedelta(days=10),
        )
        # "{username}-{bot name}" -> set of discovered group chat ids
        self._available_group_chat_ids = KeySetStore[AnyChatId](
            name="available-group-chat-ids",
            prefix=self.STORE_PREFIX,
            redis=redis,
            expiration_time=None,
            dumper=str,
            loader=parse_any_chat_id,
        )
        self.telegram_files_downloader = telegram_files_downloader

    def _full_key(self, username: str, bot_id: str) -> str:
        return f"{username}-{bot_id}"

    async def start_discovery(self, username: str, bot_id: str) -> None:
        await self._bots_in_discovery_mode_store.set_flag(self._full_key(username, bot_id))

    async def stop_discovery(self, username: str, bot_id: str) -> None:
        await self._bots_in_discovery_mode_store.unset_flag(self._full_key(username, bot_id))

    async def is_discovering(self, username: str, bot_id: str) -> bool:
        return await self._bots_in_discovery_mode_store.is_flag_set(self._full_key(username, bot_id))

    async def save_discovered_chat(self, username: str, bot_id: str, chat_id: AnyChatId) -> None:
        await self._available_group_chat_ids.add(self._full_key(username, bot_id), chat_id)

    async def get_group_chat(self, bot: AsyncTeleBot, chat_id: AnyChatId) -> Optional[TgGroupChat]:
        prefix = f"{bot.log_marker} (getting info for chat {chat_id}) "
        raw_chat: tg.Chat | None = None
        try:
            async for attempt in rate_limit_retry():
                with attempt:
                    raw_chat = await bot.get_chat(chat_id)
        except tg_api.ApiException:
            logger.info(prefix + "Error, assuming chat does not exist / is not available to bot", exc_info=True)

        if raw_chat is None:
            return None

        photo_b64: Optional[str] = None
        if raw_chat.photo is not None:
            photo_b64 = await self.telegram_files_downloader.get_base64_file(
                bot,
                file_id=raw_chat.photo.small_file_id,  # small file = 160x160 preview
            )
        return TgGroupChat(
            id=raw_chat.id,
            type=TgGroupChatType(raw_chat.type),
            title=raw_chat.title or "",
            description=raw_chat.description,
            username=raw_chat.username,
            is_forum=raw_chat.is_forum,
            photo=photo_b64,
        )

    async def validate_discovered_chats(self, owner_id: str, bot_id: str, bot: AsyncTeleBot) -> list[TgGroupChat]:
        """
        Check saved available chats and validate they are still available to the bot (i.e. it was not kicked, group chat
        was not promoted to supergroup, etc); return a list of valid chats as telegram Chat objects
        """
        prefix = f"{bot_id!r} by {owner_id!r} (validating discovered chats)"
        chats: list[TgGroupChat] = []
        key = self._full_key(owner_id, bot_id)
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

    def setup_handlers(self, owner_id: str, bot_id: str, bot: AsyncTeleBot) -> None:
        @bot.my_chat_member_handler()
        @non_capturing_handler
        async def discover_group_chats_on_add(cmu: tg.ChatMemberUpdated) -> None:
            if (
                tg_const.ChatType(cmu.chat.type) is not tg_const.ChatType.private
                and cmu.new_chat_member.status in {"creator", "administrator", "member", "restricted"}
                and await self.is_discovering(owner_id, bot_id)
            ):
                logger.info(f"Discovered chat from being added: {cmu.chat.id}")
                await self.save_discovered_chat(owner_id, bot_id, chat_id=cmu.chat.id)
            if cmu.new_chat_member.status in {"kicked", "left"}:
                logger.info(f"Undiscovered chat from being kicked: {cmu.chat.id}")
                await self._available_group_chat_ids.remove(self._full_key(owner_id, bot_id), cmu.chat.id)

        @bot.message_handler(commands=["discover_chat"])
        @non_capturing_handler
        async def discover_group_chat_on_explicit_cmd(message: tg.Message) -> None:
            if tg_const.ChatType(message.chat.type) is not tg_const.ChatType.private and await self.is_discovering(
                owner_id, bot_id
            ):
                logger.info(f"Discovered chat from explicit command: {message.chat.id}")
                await self.save_discovered_chat(owner_id, bot_id, chat_id=message.chat.id)

        @bot.message_handler(commands=["undiscover_chat"])
        @non_capturing_handler
        async def undiscover_group_chat(message: tg.Message) -> None:
            logger.info(f"Undiscovered chat from explicit command: {message.chat.id}")
            await self._available_group_chat_ids.remove(self._full_key(owner_id, bot_id), message.chat.id)

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
                    self._full_key(owner_id, bot_id),
                    message.migrate_from_chat_id,
                )
            if message.migrate_to_chat_id is not None:
                logger.info(
                    f"Migrate to chat {message.migrate_to_chat_id} message detected, undiscovering current chat"
                )
                await self._available_group_chat_ids.remove(
                    self._full_key(owner_id, bot_id),
                    message.chat.id,
                )
