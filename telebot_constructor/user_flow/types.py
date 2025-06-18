import dataclasses
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Coroutine

from telebot import AsyncTeleBot
from telebot import types as tg
from telebot.runner import AuxBotEndpoint
from telebot.types import service as service_types
from telebot.types import service as tgservice
from telebot_components.feedback import FeedbackHandler
from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.stores.banned_users import BannedUsersStore
from telebot_components.stores.language import LanguageStore

from telebot_constructor.store.errors import BotSpecificErrorsStore
from telebot_constructor.store.form_results import BotSpecificFormResultsStore
from telebot_constructor.store.media import UserSpecificMediaStore
from telebot_constructor.store.menu import MenuMetadataStore
from telebot_constructor.utils import AnyChatId


@dataclass(frozen=True)
class UserFlowSetupContext:
    bot_prefix: str
    bot: AsyncTeleBot
    redis: RedisInterface
    banned_users_store: BannedUsersStore
    form_results_store: BotSpecificFormResultsStore
    errors_store: BotSpecificErrorsStore
    language_store: LanguageStore | None
    feedback_handlers: dict[AnyChatId | None, FeedbackHandler]
    enter_block: "EnterUserFlowBlockCallback"
    get_active_block_id: "GetActiveUserFlowBlockId"
    media_store: UserSpecificMediaStore | None
    menu_metadata_store: MenuMetadataStore
    owner_chat_id: int  # Telegram chat somehow associated with the bot owner

    def make_instrumented_logger(self, module_name: str, block_id: str) -> logging.Logger:
        logger_name = module_name + f"[{self.bot_prefix}][{block_id}]"
        logger = logging.getLogger(logger_name)
        self.errors_store.instrument(logger)
        return logger

    def active_block_filter(self, block_id: str) -> tgservice.FilterFunc[tg.Message]:
        async def filter_(update_content: tg.Message) -> bool:
            current_block_id = await self.get_active_block_id(update_content.from_user.id)
            return current_block_id == block_id

        return filter_


@dataclass(frozen=True)
class MenuBlocksContext:
    updateable_message_id: int | None


@dataclass(frozen=True)
class UserFlowContext:
    bot: AsyncTeleBot
    banned_users_store: BannedUsersStore
    enter_block: "EnterUserFlowBlockCallback"
    get_active_block_id: "GetActiveUserFlowBlockId"
    chat: tg.Chat | None
    user: tg.User
    last_update_content: service_types.UpdateContent | None
    menu_blocks_ctx: MenuBlocksContext | None

    visited_block_ids: set[str] = dataclasses.field(default_factory=set[str])

    @classmethod
    def from_setup_context(
        cls,
        setup_ctx: UserFlowSetupContext,
        chat: tg.Chat | None,
        user: tg.User,
        last_update_content: service_types.UpdateContent | None,
        menu_blocks_ctx: MenuBlocksContext | None = None,
    ) -> "UserFlowContext":
        return UserFlowContext(
            bot=setup_ctx.bot,
            banned_users_store=setup_ctx.banned_users_store,
            enter_block=setup_ctx.enter_block,
            get_active_block_id=setup_ctx.get_active_block_id,
            chat=chat,
            user=user,
            last_update_content=last_update_content,
            menu_blocks_ctx=menu_blocks_ctx,
        )


UserFlowBlockId = str

EnterUserFlowBlockCallback = Callable[[UserFlowBlockId, UserFlowContext], Awaitable[None]]
GetActiveUserFlowBlockId = Callable[[int], Awaitable[UserFlowBlockId | None]]


@dataclass(frozen=True)
class BotCommandInfo:
    command: tg.BotCommand
    scope: tg.BotCommandScope | None

    def __str__(self) -> str:
        args_str = f"command={self.command.to_json()}"
        if self.scope is not None:
            args_str += f", scope={self.scope.to_json()}"
        return f"{self.__class__.__name__}({args_str})"

    def scope_key(self) -> str:
        if self.scope is not None:
            return self.scope.to_json()
        else:
            return ""


@dataclass(frozen=True)
class SetupResult:
    background_jobs: list[Coroutine[None, None, None]]
    aux_endpoints: list[AuxBotEndpoint]
    bot_commands: list[BotCommandInfo]

    @classmethod
    def empty(cls) -> "SetupResult":
        return SetupResult([], [], [])

    def merge(self, other: "SetupResult") -> None:
        self.background_jobs.extend(other.background_jobs)
        self.aux_endpoints.extend(other.aux_endpoints)
        self.bot_commands.extend(other.bot_commands)
