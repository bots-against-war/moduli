import datetime
import logging
from typing import Optional

from pydantic import BaseModel
from telebot import types as tg
from telebot_components.feedback import (
    FeedbackConfig,
    FeedbackHandler,
    ServiceMessages,
    UserAnonymization,
)
from telebot_components.feedback.anti_spam import AntiSpam, AntiSpamConfig

from telebot_constructor.user_flow.blocks.base import UserFlowBlock
from telebot_constructor.user_flow.types import (
    BotCommandInfo,
    SetupResult,
    UserFlowContext,
    UserFlowSetupContext,
)

logger = logging.getLogger(__name__)


class MessagesToUser(BaseModel):
    forwarded_to_admin_ok: str
    throttling: str


class MessagesToAdmin(BaseModel):
    copied_to_user_ok: str
    deleted_message_ok: str
    can_not_delete_message: str


class FeedbackHandlerConfig(BaseModel):
    admin_chat_id: int
    forum_topic_per_user: bool
    anonimyze_users: bool
    max_messages_per_minute: float

    messages_to_user: MessagesToUser
    messages_to_admin: MessagesToAdmin

    # hashtags config
    hashtags_in_admin_chat: bool
    unanswered_hashtag: Optional[str]
    hashtag_message_rarer_than: Optional[datetime.timedelta]

    # /log cmd config
    message_log_to_admin_chat: bool


class HumanOperatorBlock(UserFlowBlock):
    """Terminal block that incapsulates user interaction with a human operator"""

    # if set to True, all messages not catched by other handlers (e.g. forms) will be processed by this block
    catch_all: bool
    feedback_handler_config: FeedbackHandlerConfig

    async def enter(self, context: UserFlowContext) -> None:
        pass  # nothing to do on enter

    def is_catch_all(self) -> bool:
        return self.catch_all

    async def setup(self, context: UserFlowSetupContext) -> SetupResult:
        log_prefix = f"[{context.bot_prefix}]"
        logger.info(log_prefix + "Setting up feedback handler")

        async def custom_user_message_filter(message: tg.Message) -> bool:
            if self.catch_all:
                return True
            else:
                active_block_id = await context.get_active_block_id(message.from_user.id)
                return active_block_id == self.block_id

        feedback_handler = FeedbackHandler(
            admin_chat_id=self.feedback_handler_config.admin_chat_id,
            redis=context.redis,
            bot_prefix=context.bot_prefix,
            config=FeedbackConfig(
                message_log_to_admin_chat=self.feedback_handler_config.message_log_to_admin_chat,
                force_category_selection=False,
                hashtags_in_admin_chat=self.feedback_handler_config.hashtags_in_admin_chat,
                hashtag_message_rarer_than=self.feedback_handler_config.hashtag_message_rarer_than,
                unanswered_hashtag=self.feedback_handler_config.unanswered_hashtag,
                confirm_forwarded_to_admin_rarer_than=None,
                user_anonymization=(
                    UserAnonymization.FULL if self.feedback_handler_config.anonimyze_users else UserAnonymization.NONE
                ),
                forum_topic_per_user=self.feedback_handler_config.forum_topic_per_user,
                user_forum_topic_lifetime=datetime.timedelta(days=90),
                custom_user_message_filter=custom_user_message_filter,
            ),
            anti_spam=AntiSpam(
                context.redis,
                context.bot_prefix,
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
        )

        await feedback_handler.setup(context.bot)

        admin_chat_cmd_scope = tg.BotCommandScopeChat(chat_id=self.feedback_handler_config.admin_chat_id)
        return SetupResult(
            background_jobs=feedback_handler.background_jobs(base_url=None, server_listening_future=None),
            aux_endpoints=await feedback_handler.aux_endpoints(),
            bot_commands=[
                BotCommandInfo(
                    command=tg.BotCommand(command="help", description="помощь по использованию админ-чата"),
                    scope=admin_chat_cmd_scope,
                ),
                BotCommandInfo(
                    command=tg.BotCommand(command="undo", description="отменить отправку сообщения юзер:ке"),
                    scope=admin_chat_cmd_scope,
                ),
                BotCommandInfo(
                    command=tg.BotCommand(command="ban", description="забанить юзер:ку"),
                    scope=admin_chat_cmd_scope,
                ),
                BotCommandInfo(
                    command=tg.BotCommand(command="log", description="история сообщений с юзер:кой"),
                    scope=admin_chat_cmd_scope,
                ),
            ],
        )