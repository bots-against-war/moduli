import datetime
import enum
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, TypedDict

import aiohttp
from slugify import slugify
from telebot import AsyncTeleBot
from telebot import types as tg
from telebot.runner import BotRunner
from telebot_components.form.field import (
    BadFieldValueError,
    FormField,
    MessageProcessingResult,
    PlainTextField,
    SingleSelectField,
)
from telebot_components.form.form import Form
from telebot_components.form.handler import (
    FormExitContext,
    FormHandler,
    FormHandlerConfig,
)
from telebot_components.language import MaybeLanguage
from telebot_components.redis_utils.interface import RedisInterface

from telebot_constructor.app_models import SaveBotConfigVersionPayload
from telebot_constructor.bot_config import (
    BotConfig,
    UserFlowBlockConfig,
    UserFlowConfig,
    UserFlowEntryPointConfig,
    UserFlowNodePosition,
)
from telebot_constructor.client.client import TrustedModuliApiClient
from telebot_constructor.user_flow.blocks.content import (
    Content,
    ContentBlock,
    ContentText,
    TextMarkup,
)
from telebot_constructor.user_flow.blocks.human_operator import (
    FeedbackHandlerConfig,
    HumanOperatorBlock,
    MessagesToAdmin,
    MessagesToUser,
)
from telebot_constructor.user_flow.entrypoints.command import CommandEntryPoint


async def load_bot_display_name(token: str) -> str | None:
    bot = AsyncTeleBot(token=token)
    try:
        return (await bot.get_me()).full_name
    except Exception:
        return None


@dataclass
class BotTokenField(FormField[str]):
    async def process_message(
        self,
        message: tg.Message,
        language: MaybeLanguage,
        dynamic_data: Any,
    ) -> MessageProcessingResult[str]:
        token = message.text_content
        if await load_bot_display_name(token):
            return MessageProcessingResult(
                response_to_user=None,
                parsed_value=token,
            )
        else:
            return MessageProcessingResult(
                response_to_user="Проверьте валидность токена!",
                parsed_value=None,
            )


class HtmlTextField(PlainTextField):
    def parse(self, message):
        text = message.html_text
        if not text:
            raise BadFieldValueError(self.empty_text_error_msg)
        return text


class AnonymizeUsers(enum.Enum):
    YES = "Да"
    NO = "Нет"


moduli_client_form = Form.branching(
    [
        BotTokenField(name="token", required=True, query_message="Пришлите токен бота."),
        HtmlTextField(
            name="welcome",
            required=True,
            query_message="Введите приветственное сообщение.",
            empty_text_error_msg="Сообщение не может быть пустым!",
        ),
        SingleSelectField(
            name="anonymize",
            required=True,
            query_message="Анонимизировать пользователей?",
            EnumClass=AnonymizeUsers,
            invalid_enum_value_error_msg="Используйте меню!",
            menu_row_width=2,
        ),
    ]
)


class ModuliClientFormResult(TypedDict):
    token: str
    welcome: str
    admin_chat_id: int
    anonymize: AnonymizeUsers


moduli_client_form.validate_result_type(ModuliClientFormResult)


def setup_moduli_bot(
    bot: AsyncTeleBot,
    bot_prefix: str,
    redis: RedisInterface,
    main_flow_cmd: str,
    api: TrustedModuliApiClient,
) -> None:
    """Simple bot interface to telebot constructor, providing livegram-like frontend to create feedback bots"""
    form_handler = FormHandler[ModuliClientFormResult, Any](
        redis=redis,
        bot_prefix=bot_prefix,
        name="moduli-client-form",
        form=moduli_client_form,
        config=FormHandlerConfig(
            form_starting_template="Создайте бота!\n\n {} – отменить создание бота.",
            echo_filled_field=False,
            retry_field_msg="Исправьте значение!",
            unsupported_cmd_error_template="",
            can_skip_field_template="",
            cancelling_because_of_error_template="",
            cant_skip_field_msg="",
        ),
    )

    async def complete_form(context: FormExitContext[ModuliClientFormResult]) -> None:
        user = context.last_update.from_user

        token = context.result["token"]
        anonymize_users = context.result["anonymize"] is AnonymizeUsers.YES
        bot_name = await load_bot_display_name(token)
        if bot_name is None:
            await bot.send_message(
                chat_id=user.id,
                text="Что-то не так с вашим токеном, проверьте его валидность и заполните форму ещё раз!",
            )
            return

        bot_id = slugify(bot_name, max_length=64, word_boundary=True) + "-" + str(uuid.uuid4())[:8]
        token_secret_name = f"token-for-{bot_id}"
        if not await api.create_secret(user, name=token_secret_name, value=token):
            await bot.send_message(user.id, text="Не получилось создать бота...")
            return

        start_cmd_id = "default-start-command"
        welcome_msg_block_id = "welcome-msg-content"
        feedback_block_id = "feedback"
        config = BotConfig(
            token_secret_name=token_secret_name,
            user_flow_config=UserFlowConfig(
                entrypoints=[
                    UserFlowEntryPointConfig(
                        command=CommandEntryPoint(
                            entrypoint_id=start_cmd_id,
                            command="start",
                            next_block_id=welcome_msg_block_id,
                        ),
                    )
                ],
                blocks=[
                    UserFlowBlockConfig(
                        content=ContentBlock(
                            block_id=welcome_msg_block_id,
                            contents=[
                                Content(
                                    text=ContentText(
                                        text=context.result["welcome"],
                                        markup=TextMarkup.HTML,
                                    ),
                                    attachments=[],
                                )
                            ],
                            next_block_id=feedback_block_id,
                        )
                    ),
                    UserFlowBlockConfig(
                        human_operator=HumanOperatorBlock(
                            block_id=feedback_block_id,
                            feedback_handler_config=FeedbackHandlerConfig(
                                admin_chat_id=context.result["admin_chat_id"],
                                forum_topic_per_user=False,
                                anonimyze_users=anonymize_users,
                                max_messages_per_minute=15,
                                messages_to_user=MessagesToUser(
                                    forwarded_to_admin_ok=(
                                        "Переслано с сохранением вашей анонимности! Для полной безопасности "
                                        + "вы можете удалить переписку со своей стороны."
                                        if anonymize_users
                                        else "Переслано!"
                                    ),
                                    throttling="Не присылайте больше {} сообщений в минуту!",
                                ),
                                messages_to_admin=MessagesToAdmin(
                                    copied_to_user_ok="Передано!",
                                    deleted_message_ok="Сообщение удалено!",
                                    can_not_delete_message="Не получилось удалить сообщение!",
                                ),
                                hashtags_in_admin_chat=False,
                                unanswered_hashtag=None,
                                hashtag_message_rarer_than=None,
                                message_log_to_admin_chat=False,
                                confirm_forwarded_to_admin_rarer_than=(
                                    datetime.timedelta(hours=1) if anonymize_users else None
                                ),
                            ),
                            catch_all=False,
                        ),
                    ),
                ],
                node_display_coords={
                    "bot-info-node": UserFlowNodePosition(x=0, y=-200),
                    start_cmd_id: UserFlowNodePosition(x=0, y=0),
                    welcome_msg_block_id: UserFlowNodePosition(x=0, y=200),
                    feedback_block_id: UserFlowNodePosition(x=0, y=400),
                },
            ),
        )
        if not await api.save_and_start_bot(
            user=user,
            bot_id=bot_id,
            payload=SaveBotConfigVersionPayload(
                config=config,
                version_message="initial version from bot",
                start=True,
                display_name=bot_name,
            ),
        ):
            await bot.send_message(user.id, "Не получилось создать бота...")
            return
        await bot.send_message(user.id, "Бот создан, ура!")

    async def cancel_form(context: FormExitContext) -> None:
        await bot.send_message(
            chat_id=context.last_update.from_user.id,
            text="Приходите в другой раз",
        )

    form_handler.setup(bot, on_form_completed=complete_form, on_form_cancelled=complete_form)

    @bot.message_handler(commands=[main_flow_cmd])
    async def start_form(m: tg.Message) -> None:
        await form_handler.start(bot, m.from_user)


if __name__ == "__main__":
    import asyncio

    from telebot_components.redis_utils.emulation import PersistentRedisEmulation

    async def main() -> None:
        logging.basicConfig(level=logging.INFO)

        redis = PersistentRedisEmulation(dirname=".moduli-bot-storage")  # type: ignore

        token = os.environ["MODULI_CLIENT_BOT_TOKEN"]
        bot = AsyncTeleBot(token=token)
        bot_prefix = "modulie-client-test"
        print(await bot.get_me())

        async with aiohttp.ClientSession() as session:
            api = TrustedModuliApiClient(
                aiohttp_session=session,
                base_url=os.environ["MODULI_API_URL"],
                trusted_client_token=os.environ["MODULI_API_TOKEN"],
            )
            await api.ping()

            setup_moduli_bot(
                bot,
                bot_prefix=bot_prefix,
                redis=redis,
                main_flow_cmd="start",
                api=api,
            )

            runner = BotRunner(bot_prefix=bot_prefix, bot=bot)
            await runner.run_polling()

    asyncio.run(main())
