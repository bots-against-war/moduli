import datetime
import enum
import logging
import os
import textwrap
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypedDict

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
from telebot_components.utils import html_link

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


async def load_bot_user(token: str) -> tg.User | None:
    bot = AsyncTeleBot(token=token)
    try:
        return await bot.get_me()
    except Exception:
        return None


def preproc_text(t: str) -> str:
    return textwrap.dedent(t).strip()


@dataclass
class BotTokenField(FormField[str]):
    async def process_message(
        self,
        message: tg.Message,
        language: MaybeLanguage,
        dynamic_data: Any,
    ) -> MessageProcessingResult[str]:
        token = message.text_content
        if await load_bot_user(token):
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
        BotTokenField(
            name="token",
            required=True,
            query_message=preproc_text(
                """
                (1/3) Создайте бота

                • Перейдите в @BotFather
                • Введите команду /newbot
                • Дайте боту имя и @юзернейм
                • Получите токен вашего бота (выглядит так: <code>4839574812:AAFD39kkdpWt3ywyRZergyOLMaJhac60qc</code>), скопируйте и пришлите в этот чат.

                Не подключайте боты, которые используются в других сервисах (Livegram, Dialogflow, и других).
                """  # noqa: E501
            ),
        ),
        HtmlTextField(
            name="welcome",
            required=True,
            query_message="(2/3) Напишите сообщение, которое будет появляться сразу после кнопки “start”.",
            empty_text_error_msg="Сообщение не может быть пустым!",
        ),
        SingleSelectField(
            name="anonymize",
            required=True,
            query_message="(3/3) Создатели бота всегда анонимны. Если вы хотите скрывать идентичность ваших собеседни:ц, мы советуем включить режим анонимизации – вы сможете отвечать им, но не увидите их имя и @юзернейм. Включить?",  # noqa: E501
            EnumClass=AnonymizeUsers,
            invalid_enum_value_error_msg="Используйте кнопки меню для ответа! Если вы не видите кнопки, нажмите на иконку с 5 точками рядом с полем ввода.",  # noqa: E501
            menu_row_width=2,
        ),
    ]
)


class ModuliClientFormResult(TypedDict):
    token: str
    welcome: str
    anonymize: AnonymizeUsers


moduli_client_form.validate_result_type(ModuliClientFormResult)


def moduli_bot_form_handler(
    bot: AsyncTeleBot,
    bot_prefix: str,
    redis: RedisInterface,
    api: TrustedModuliApiClient,
    after: Callable[[tg.User], Awaitable[Any]] | None = None,
) -> FormHandler:
    """Simple bot interface to telebot constructor, providing livegram-like frontend to create feedback bots"""

    form_handler = FormHandler[ModuliClientFormResult, Any](
        redis=redis,
        bot_prefix=bot_prefix,
        name="moduli-client-form",
        form=moduli_client_form,
        config=FormHandlerConfig(
            form_starting_template="",
            echo_filled_field=False,
            retry_field_msg="Исправьте значение!",
            unsupported_cmd_error_template="",
            can_skip_field_template="",
            cancelling_because_of_error_template="Unexpected error, exiting form: {}",
            cant_skip_field_msg="",
        ),
    )

    async def complete_form(context: FormExitContext[ModuliClientFormResult]) -> None:
        user = context.last_update.from_user

        token = context.result["token"]
        anonymize_users = context.result["anonymize"] is AnonymizeUsers.YES
        bot_user = await load_bot_user(token)
        if bot_user is None:
            await bot.send_message(
                chat_id=user.id,
                text="Что-то не так с вашим токеном, проверьте его валидность и заполните форму ещё раз!",
            )
            return
        bot_name = bot_user.full_name

        moduli_bot_id = slugify(bot_name, max_length=64, word_boundary=True) + "-" + str(uuid.uuid4())[:8]
        token_secret_name = f"token-for-{moduli_bot_id}"
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
                                admin_chat_id=None,
                                forum_topic_per_user=False,
                                anonimyze_users=anonymize_users,
                                max_messages_per_minute=15,
                                messages_to_user=MessagesToUser(
                                    forwarded_to_admin_ok=(
                                        "Сообщение передано с сохранением вашей анонимности. "
                                        + "Рекомендуем регулярно удалять чувствительную переписку – "
                                        + "бот не может сделать это за вас."
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
            bot_id=moduli_bot_id,
            payload=SaveBotConfigVersionPayload(
                config=config,
                version_message="initial version from bot",
                start=True,
                display_name=bot_name,
            ),
        ):
            await bot.send_message(user.id, "Не получилось создать бота...")
            return
        await bot.send_message(
            user.id,
            f"Браво! Ваш бот @{bot_user.username} запущен – "
            + 'для проверки нажмите "start" и напишите ему любое сообщение.',
        )
        await asyncio.sleep(0.15)
        studio_link = api.base_url.strip("/") + f"/studio/{moduli_bot_id}"
        await bot.send_message(
            user.id,
            "Сообщения от пользователь:ниц бот будут приходить в этот чат. Ответы на них "
            + "(по свайпу влево или двойному нажатию) отправляются от лица бота.\n\n"
            + f"В {html_link(text='веб-версии конструктора', href=studio_link)} можно подключить админ-чат, "
            + "где сообщения смогут обрабатывать несколько человек. Там же доступно редактирование бота "
            + "и более сложные сценарии использования.",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        if after is not None:
            await after(user)

    async def cancel_form(context: FormExitContext) -> None:
        user = context.last_update.from_user
        await bot.send_message(
            chat_id=user.id,
            text="Вы можете всегда вернуться к конструктору!",
        )
        if after is not None:
            await after(user)

    form_handler.setup(bot, on_form_completed=complete_form, on_form_cancelled=cancel_form)

    return form_handler


if __name__ == "__main__":
    import asyncio

    from telebot_components.redis_utils.emulation import PersistentRedisEmulation

    async def main() -> None:
        logging.basicConfig(level=logging.INFO)

        redis = PersistentRedisEmulation(dirname=".moduli-bot-storage")  # type: ignore

        token = os.environ["MODULI_CLIENT_BOT_TOKEN"]
        bot = AsyncTeleBot(token=token)
        bot_prefix = "moduli-client-test"
        print(await bot.get_me())

        async with aiohttp.ClientSession() as session:
            api = TrustedModuliApiClient(
                aiohttp_session=session,
                base_url=os.environ["MODULI_API_URL"],
                trusted_client_token=os.environ["MODULI_API_TOKEN"],
            )
            await api.ping()

            form_handler = moduli_bot_form_handler(
                bot,
                bot_prefix=bot_prefix,
                redis=redis,
                api=api,
            )

            @bot.message_handler(commands=["start"])
            async def start_form(m: tg.Message) -> None:
                await form_handler.start(bot, m.from_user)

            runner = BotRunner(bot_prefix=bot_prefix, bot=bot)
            await runner.run_polling()

    asyncio.run(main())
