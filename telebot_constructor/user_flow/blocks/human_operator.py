import datetime
from typing import Any, Optional

from pydantic import BaseModel
from telebot import types as tg
from telebot_components.feedback import (
    FeedbackConfig,
    FeedbackHandler,
    ServiceMessages,
    UserAnonymization,
)
from telebot_components.feedback.anti_spam import AntiSpam, AntiSpamConfig
from telebot_components.utils import emoji_hash

from telebot_constructor.user_flow.blocks.base import UserFlowBlock
from telebot_constructor.user_flow.types import (
    BotCommandInfo,
    SetupResult,
    UserFlowContext,
    UserFlowSetupContext,
)
from telebot_constructor.utils.pydantic import LocalizableText


class MessagesToUser(BaseModel):
    forwarded_to_admin_ok: LocalizableText
    throttling: LocalizableText


class MessagesToAdmin(BaseModel):
    copied_to_user_ok: str
    deleted_message_ok: str
    can_not_delete_message: str


class FeedbackHandlerConfig(BaseModel):
    admin_chat_id: int | None
    forum_topic_per_user: bool
    anonimyze_users: bool
    max_messages_per_minute: float

    messages_to_user: MessagesToUser
    messages_to_admin: MessagesToAdmin

    # hashtags config
    hashtags_in_admin_chat: bool
    unanswered_hashtag: str | None
    hashtag_message_rarer_than: datetime.timedelta | None

    # /log cmd config
    message_log_to_admin_chat: bool

    confirm_forwarded_to_admin_rarer_than: datetime.timedelta | None = None


class HumanOperatorBlock(UserFlowBlock):
    """Terminal block that incapsulates user interaction with a human operator"""

    # if set to True, all messages not catched by other handlers (e.g. forms) will be processed by this block
    catch_all: bool
    feedback_handler_config: FeedbackHandlerConfig

    def model_post_init(self, __context: Any) -> None:
        self._feedback_handler: Optional[FeedbackHandler] = None

    def possible_next_block_ids(self) -> list[str]:
        return []

    @property
    def feedback_handler(self) -> FeedbackHandler:
        if self._feedback_handler is None:
            raise RuntimeError("Attempt to get feedback handler before it is set up")
        return self._feedback_handler

    async def enter(self, context: UserFlowContext) -> None:
        pass  # nothing to do on enter

    def is_catch_all(self) -> bool:
        return self.catch_all

    async def setup(self, context: UserFlowSetupContext) -> SetupResult:
        async def custom_user_message_filter(message: tg.Message) -> bool:
            if self.catch_all:
                return True
            else:
                active_block_id = await context.get_active_block_id(message.from_user.id)
                return active_block_id == self.block_id

        admin_chat_id = self.feedback_handler_config.admin_chat_id or context.owner_chat_id
        self._feedback_handler = FeedbackHandler(
            admin_chat_id=admin_chat_id,
            name=f"fh-{admin_chat_id}",
            redis=context.redis,
            bot_prefix=context.bot_prefix,
            config=FeedbackConfig(
                message_log_to_admin_chat=self.feedback_handler_config.message_log_to_admin_chat,
                force_category_selection=False,
                hashtags_in_admin_chat=self.feedback_handler_config.hashtags_in_admin_chat,
                hashtag_message_rarer_than=self.feedback_handler_config.hashtag_message_rarer_than,
                unanswered_hashtag=self.feedback_handler_config.unanswered_hashtag,
                confirm_forwarded_to_admin_rarer_than=(
                    self.feedback_handler_config.confirm_forwarded_to_admin_rarer_than
                ),
                user_anonymization=(
                    UserAnonymization.FULL if self.feedback_handler_config.anonimyze_users else UserAnonymization.NONE
                ),
                forum_topic_per_user=self.feedback_handler_config.forum_topic_per_user,
                user_forum_topic_lifetime=datetime.timedelta(days=90),
                custom_user_message_filter=custom_user_message_filter,
                user_id_hash_func=bracketed_emoji_hash,
            ),
            anti_spam=AntiSpam(
                redis=context.redis,
                bot_prefix=context.bot_prefix,
                name=str(self.feedback_handler_config.admin_chat_id),
                config=AntiSpamConfig(
                    throttle_after_messages=int(5 * self.feedback_handler_config.max_messages_per_minute),
                    throttle_duration=datetime.timedelta(minutes=5),
                    soft_ban_after_throttle_violations=10,
                    soft_ban_duration=datetime.timedelta(days=1),
                ),
            ),
            service_messages=ServiceMessages(
                forwarded_to_admin_ok=self.feedback_handler_config.messages_to_user.forwarded_to_admin_ok,
                you_must_select_category=None,
                throttling_template=self.feedback_handler_config.messages_to_user.throttling,
                copied_to_user_ok=self.feedback_handler_config.messages_to_admin.copied_to_user_ok,
                can_not_delete_message=self.feedback_handler_config.messages_to_admin.can_not_delete_message,
                deleted_message_ok=self.feedback_handler_config.messages_to_admin.deleted_message_ok,
            ),
            banned_users_store=context.banned_users_store,
            language_store=context.language_store,
        )
        context.errors_store.instrument(self._feedback_handler.logger)

        await self._feedback_handler.setup(context.bot)

        admin_chat_cmd_scope = tg.BotCommandScopeChat(chat_id=admin_chat_id)
        return SetupResult(
            background_jobs=self._feedback_handler.background_jobs(base_url=None, server_listening_future=None),
            aux_endpoints=await self._feedback_handler.aux_endpoints(),
            bot_commands=[
                BotCommandInfo(
                    command=tg.BotCommand(command="help", description="помощь по использованию рабочего чата"),
                    scope=admin_chat_cmd_scope,
                ),
                BotCommandInfo(
                    command=tg.BotCommand(command="undo", description="отменить отправку сообщения пользователь:нице"),
                    scope=admin_chat_cmd_scope,
                ),
                BotCommandInfo(
                    command=tg.BotCommand(command="ban", description="забанить пользователь:ницу"),
                    scope=admin_chat_cmd_scope,
                ),
                BotCommandInfo(
                    command=tg.BotCommand(command="log", description="история сообщений с пользователь:ницей"),
                    scope=admin_chat_cmd_scope,
                ),
            ],
        )


def bracketed_emoji_hash(user_id: int, bot_prefix: str) -> str:
    return "(" + emoji_hash(user_id, bot_prefix, length=6) + ")"
