"""Pydantic models for various app endpoints"""

import enum

from pydantic import BaseModel, Field, TypeAdapter
from telebot import AsyncTeleBot
from telebot import types as tg

from telebot_constructor.bot_config import BotConfig
from telebot_constructor.store.errors import BotError
from telebot_constructor.store.form_results import FormInfo, FormInfoBasic, FormResult
from telebot_constructor.store.types import BotConfigVersionMetadata, BotEvent
from telebot_constructor.telegram_files_downloader import TelegramFilesDownloader
from telebot_constructor.utils.rate_limit_retry import rate_limit_retry


class BotTokenPayload(BaseModel):
    token: str


class BotTokenValidationResult(BaseModel):
    name: str
    username: str
    suggested_bot_id: str
    is_used: bool


class TgGroupChatType(enum.Enum):
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"


class TgGroupChat(BaseModel):
    """pydantic projection of https://core.telegram.org/bots/api#chat"""

    id: int
    type: TgGroupChatType
    title: str
    description: str | None
    username: str | None
    is_forum: bool | None
    photo: str | None  # if set, base64-encoded chat photo


class TgBotCommand(BaseModel):
    command: str
    description: str


class TgBotUser(BaseModel):
    """Info on telegram bot, combining info from several Bot API endpoints"""

    id: int

    # as returned by getMe
    username: str

    # as returned by getMyXxx, potentially localizable (we're not using this for now though)
    name: str
    description: str
    short_description: str

    can_join_groups: bool
    can_read_all_group_messages: bool

    commands: list[TgBotCommand]

    userpic: str | None  # base64-encoded bot's avatar photo preview

    @classmethod
    async def fetch(cls, bot: AsyncTeleBot, telegram_files_downloader: TelegramFilesDownloader) -> "TgBotUser":
        """Fetch data from Telegram Bot API and compose TgBotUser object"""
        async for attempt in rate_limit_retry():
            with attempt:
                bot_user = await bot.get_me()
        async for attempt in rate_limit_retry():
            with attempt:
                bot_description = await bot.get_my_description()
        async for attempt in rate_limit_retry():
            with attempt:
                bot_short_description = await bot.get_my_short_description()
        async for attempt in rate_limit_retry():
            with attempt:
                bot_commands_raw = await bot.get_my_commands(scope=None, language_code=None)
                bot_commands = [TgBotCommand(**bc.to_dict()) for bc in bot_commands_raw]
        async for attempt in rate_limit_retry():
            with attempt:
                bot_name_obj = await bot.get_my_name()
                bot_name = bot_name_obj.name if bot_name_obj is not None else None
        async for attempt in rate_limit_retry():
            with attempt:
                bot_user_profile_photos = await bot.get_user_profile_photos(bot_user.id, limit=1)
                bot_userpic_b64: str | None = None
                if bot_user_profile_photos.photos:
                    userpic_photos: list[list[tg.PhotoSize]] = bot_user_profile_photos.photos  # type: ignore
                    bot_userpic_b64 = await telegram_files_downloader.get_base64_file(
                        bot=bot,
                        file_id=min(userpic_photos[0], key=lambda photo_size: photo_size.width).file_id,
                    )
        return TgBotUser(
            id=bot_user.id,
            name=bot_name or bot_user.first_name,
            username=bot_user.username or "",
            description=bot_description.description if bot_description is not None else "",
            short_description=bot_short_description.short_description if bot_short_description is not None else "",
            userpic=bot_userpic_b64,
            commands=bot_commands,
            can_join_groups=bot_user.can_join_groups or False,
            can_read_all_group_messages=bot_user.can_read_all_group_messages or False,
        )


class TgBotUserUpdate(BaseModel):
    name: str
    description: str
    short_description: str

    async def save(self, bot: AsyncTeleBot, telegram_files_downloader: TelegramFilesDownloader) -> None:
        """Upload data stored in the object to Telegram"""
        existing_bot_user = await TgBotUser.fetch(bot, telegram_files_downloader)
        if self.name != existing_bot_user.name:
            async for attempt in rate_limit_retry():
                with attempt:
                    await bot.set_my_name(name=self.name)
        if self.description != existing_bot_user.description:
            async for attempt in rate_limit_retry():
                with attempt:
                    await bot.set_my_description(description=self.description)
        if self.short_description != existing_bot_user.short_description:
            async for attempt in rate_limit_retry():
                with attempt:
                    await bot.set_my_short_description(short_description=self.short_description)


class AuthType(enum.Enum):
    NO_AUTH = "no_auth"
    TELEGRAM_GROUP_AUTH = "tg_group_auth"
    TELEGRAM_AUTH = "tg_auth"


class LoggedInUser(BaseModel):
    auth_type: AuthType
    username: str  # internal username, not user-visible
    name: str
    display_username: str | None = None
    userpic: str | None = None


class UpdateBotDisplayNamePayload(BaseModel):
    display_name: str = Field(max_length=512)


class BotVersionInfo(BaseModel):
    version: int  # zero-based index of a version
    metadata: BotConfigVersionMetadata


class BotInfo(BaseModel):
    bot_id: str  # internal constructor bot id
    display_name: str  # user-facing name
    running_version: int | None  # None = bot not running
    running_version_info: BotVersionInfo | None  # None = bot not running
    last_versions: list[BotVersionInfo]  # versions, including last and running (if present) versions
    last_events: list[BotEvent]
    forms_with_responses: list[FormInfoBasic]
    last_errors: list[BotError]
    admin_chat_ids: list[str | int]
    alert_chat_id: str | int | None


BotInfoList = TypeAdapter(list[BotInfo])


class SaveBotConfigVersionPayload(BaseModel):
    config: BotConfig
    version_message: str | None
    start: bool
    display_name: str | None = None  # to update display name together with config


class StartBotPayload(BaseModel):
    version: int  # passed directly to versioned store, i.e. values like -1 are supported


class SetAlertChatIdPayload(BaseModel):
    alert_chat_id: int | str
    test: bool = False


class FormResultsPage(BaseModel):
    bot_info: BotInfo
    info: FormInfo
    results: list[FormResult]


class BotErrorsPage(BaseModel):
    bot_info: BotInfo
    errors: list[BotError]


class BotVersionsPage(BaseModel):
    bot_info: BotInfo
    versions: list[BotVersionInfo]
    total_versions: int
