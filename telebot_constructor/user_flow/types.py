import dataclasses
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Coroutine, Optional

from telebot import AsyncTeleBot
from telebot import types as tg
from telebot.runner import AuxBotEndpoint
from telebot.types import service as service_types
from telebot_components.feedback import FeedbackHandler
from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.stores.banned_users import BannedUsersStore
from telebot_components.stores.language import LanguageStore

from telebot_constructor.store.errors import BotSpecificErrorsStore
from telebot_constructor.store.form_results import BotSpecificFormResultsStore
from telebot_constructor.store.media import UserSpecificMediaStore
from telebot_constructor.utils import AnyChatId


@dataclass(frozen=True)
class UserFlowSetupContext:
    bot_prefix: str
    bot: AsyncTeleBot
    redis: RedisInterface
    banned_users_store: BannedUsersStore
    form_results_store: BotSpecificFormResultsStore
    errors_store: BotSpecificErrorsStore
    language_store: Optional[LanguageStore]
    feedback_handlers: dict[AnyChatId | None, FeedbackHandler]
    enter_block: "EnterUserFlowBlockCallback"
    get_active_block_id: "GetActiveUserFlowBlockId"
    media_store: UserSpecificMediaStore | None
    owner_chat_id: int  # Telegram chat somehow associated with the bot owner

    def make_instrumented_logger(self, module_name: str) -> logging.Logger:
        logger = logging.getLogger(module_name + f"[{self.bot_prefix}]")
        self.errors_store.instrument(logger)
        return logger


@dataclass(frozen=True)
class UserFlowContext:
    bot: AsyncTeleBot
    banned_users_store: BannedUsersStore
    enter_block: "EnterUserFlowBlockCallback"
    get_active_block_id: "GetActiveUserFlowBlockId"
    chat: Optional[tg.Chat]
    user: tg.User
    last_update_content: Optional[service_types.UpdateContent]

    visited_block_ids: set[str] = dataclasses.field(default_factory=set)

    @classmethod
    def from_setup_context(
        cls,
        setup_ctx: UserFlowSetupContext,
        chat: Optional[tg.Chat],
        user: tg.User,
        last_update_content: Optional[service_types.UpdateContent],
    ) -> "UserFlowContext":
        return UserFlowContext(
            bot=setup_ctx.bot,
            banned_users_store=setup_ctx.banned_users_store,
            enter_block=setup_ctx.enter_block,
            get_active_block_id=setup_ctx.get_active_block_id,
            chat=chat,
            user=user,
            last_update_content=last_update_content,
        )


UserFlowBlockId = str

EnterUserFlowBlockCallback = Callable[[UserFlowBlockId, UserFlowContext], Awaitable[None]]
GetActiveUserFlowBlockId = Callable[[int], Awaitable[Optional[UserFlowBlockId]]]


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
