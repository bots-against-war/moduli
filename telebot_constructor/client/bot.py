import asyncio
import datetime
import enum
import logging
import os
import textwrap
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypedDict

import aiohttp
from telebot import AsyncTeleBot
from telebot import types as tg
from telebot.runner import BotRunner
from telebot_components.form.field import (
    FormField,
    MessageProcessingContext,
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
from telebot_components.language import (
    Language,
    MultilangText,
    any_language_to_language_data,
)
from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.stores.language import (
    LanguageSelectionMenuConfig,
    LanguageStore,
)
from telebot_components.utils import html_link

from telebot_constructor.app_models import SaveBotConfigVersionPayload
from telebot_constructor.bot_config import (
    BotConfig,
    UserFlowBlockConfig,
    UserFlowConfig,
    UserFlowEntryPointConfig,
    UserFlowNodePosition,
)
from telebot_constructor.client.client import (
    TrustedModuliApiClient,
    TrustedModuliApiClientConfig,
)
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


def preproc_text(t: str) -> str:
    return textwrap.dedent(t).strip()


@dataclass
class BotTokenField(FormField[str]):
    async def process_message(self, context: MessageProcessingContext[str]) -> MessageProcessingResult[str]:
        assert context.language is not None
        lang = any_language_to_language_data(context.language)
        token = context.message.text_content.strip()

        async with aiohttp.ClientSession() as session:
            api = TrustedModuliApiClient(session, config=context.dynamic_data)
            res = await api.validate_token(user=context.message.from_user, token=token)

        if res is None:
            return MessageProcessingResult(
                response_to_user={
                    Language.RU.as_data(): "Проверьте валидность токена!",
                    Language.EN.as_data(): "Check token validity!",
                }[lang],
                new_field_value=None,
                complete_field=False,
            )
        if res.is_used:
            return MessageProcessingResult(
                response_to_user={
                    Language.RU.as_data(): (
                        "Токен уже использован для создания бота! Создайте нового бота или "
                        + "новый токен для существующего в @BotFather."
                    ),
                    Language.EN.as_data(): (
                        "Token has already been used to create a bot! Create a new bot or a new token for an existing one in @BotFather."
                    ),
                }[lang],
                new_field_value=None,
                complete_field=False,
            )
        return MessageProcessingResult(
            response_to_user=None,
            new_field_value=token,
            complete_field=True,
        )


class AnonymizeUsers(enum.Enum):
    YES = {Language.RU: "Да", Language.EN: "Yes"}
    NO = {Language.RU: "Нет", Language.EN: "No"}


class ModuliClientFormResult(TypedDict):
    token: str
    welcome: str
    anonymize: AnonymizeUsers


def moduli_bot_form_handler(
    bot: AsyncTeleBot,
    bot_prefix: str,
    redis: RedisInterface,
    api: TrustedModuliApiClient,
    language_store: LanguageStore,
    after: Callable[[tg.User], Awaitable[Any]] | None = None,
) -> FormHandler[ModuliClientFormResult, TrustedModuliApiClientConfig]:
    """Simple bot interface to telebot constructor, providing livegram-like frontend to create feedback bots"""

    def trivial_multilang(s: str) -> MultilangText:
        # TODO: make this a method on language store
        return {lang: s for lang in language_store.languages}

    moduli_client_form = Form.branching(
        [
            BotTokenField(
                name="token",
                required=True,
                query_message={
                    Language.RU: preproc_text(
                        """
                        (1/3) Создайте бота
    
                        • Перейдите в @BotFather
                        • Введите команду /​newbot
                        • Дайте боту имя и @юзернейм
                        • Получите токен вашего бота (выглядит так: <code>5262203209:AAAAt7KnBmUYrufsiNi9sP5RWnmXA6zaXA</code>), скопируйте и пришлите в этот чат.

                        Не подключайте боты, которые используются в других сервисах (Livegram, Fleep и т.д.).
                        """
                    ),
                    Language.EN: preproc_text(
                        """
                        (1/3) Create the bot
    
                        • Go to @BotFather
                        • Enter /​newbot command
                        • Give bot a name and a @​username
                        • You will receive a token (looks like this: <code>5262203209:AAAAt7KnBmUYrufsiNi9sP5RWnmXA6zaXA</code>); copy it and send to this chat.

                        Do not connect bots that are already used in other services (Livegram, Fleep, etc).
                        """
                    ),
                },
            ),
            PlainTextField(
                name="welcome",
                required=True,
                query_message={
                    Language.RU: "(2/3) Напишите приветственное сообщение, которое будет появляться сразу после кнопки “start”.",
                    Language.EN: "(2/3) Create a welcome message that will appear after the “start” button.",
                },
                empty_text_error_msg={
                    Language.RU: "Сообщение не может быть пустым!",
                    Language.EN: "The message can't be empty!",
                },
            ),
            SingleSelectField(
                name="anonymize",
                required=True,
                query_message={
                    Language.RU: "(3/3) Создатели бота всегда анонимны. Если вы хотите скрывать идентичность ваших собеседни:ц, мы советуем включить режим анонимизации – вы сможете отвечать им, но не увидите их имя и @юзернейм. Включить?",
                    Language.EN: "(3/3) As bot creators you will remain anonymous. If you want to hide the identity of your interlocutors, we recommend the anonymization mode - you will be able to reply to them, but will not see their name and @​username. Turn it on?",
                },
                EnumClass=AnonymizeUsers,
                invalid_enum_value_error_msg={
                    Language.RU: "Используйте кнопки меню для ответа! Если вы не видите кнопки, нажмите на иконку с 4 точками рядом с полем ввода.",
                    Language.EN: "Use the menu to answer! If you don't see menu buttons, click the 4 dots icon next to the input field.",
                },
                menu_row_width=2,
            ),
        ]
    )

    form_handler = FormHandler[ModuliClientFormResult, Any](
        redis=redis,
        bot_prefix=bot_prefix,
        name="moduli-client-form",
        form=moduli_client_form,
        config=FormHandlerConfig(
            form_starting_template={
                Language.RU: (
                    "Создание бота займет несколько минут и состоит из трех шагов.\n\n"
                    + "Если вы захотите прервать создание бота, используйте команду {} – мы удалим все данные."
                ),
                Language.EN: (
                    "Creating a bot will take several minutes and consists of three steps.\n\n"
                    + "If you want to cancel the creation of the bot, use the {} command - we will delete all data."
                ),
            },
            echo_filled_field=False,
            retry_field_msg=trivial_multilang(""),
            unsupported_cmd_error_template=trivial_multilang(""),
            can_skip_field_template=trivial_multilang(""),
            cancelling_because_of_error_template=trivial_multilang("Unexpected error, exiting: {}"),
            cant_skip_field_msg=trivial_multilang(""),
        ),
        language_store=language_store,
    )

    async def complete_form(context: FormExitContext[ModuliClientFormResult]) -> None:
        user = context.last_update.from_user
        admin_lang = await language_store.get_user_language(user)

        token = context.result["token"]
        anonymize_users = context.result["anonymize"] is AnonymizeUsers.YES

        res = await api.validate_token(user=user, token=token)
        if res is None or res.is_used:
            await bot.send_message(
                chat_id=user.id,
                text={
                    Language.RU.as_data(): "Что-то не так с вашим токеном, проверьте его валидность и попробуйте ещё раз!",
                    Language.RU.as_data(): "There is something wrong with your token, please check its validity and try again!",
                }[admin_lang],
            )
            return
        bot_name = res.name
        moduli_bot_id = res.suggested_bot_id
        bot_username = res.username

        token_secret_name = f"token-for-{moduli_bot_id}"
        if not await api.create_token_secret(user, name=token_secret_name, value=token):
            await bot.send_message(
                user.id,
                text={
                    Language.RU.as_data(): "Не получилось создать бота...",
                    Language.EN.as_data(): "Failed to create a bot...",
                }[admin_lang],
            )
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
                                        markup=TextMarkup.NONE,
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
                                        {
                                            Language.RU.as_data(): "Отправлено анонимно!\n\nРекомендуем регулярно удалять чувствительную переписку – бот не может сделать это за вас.",
                                            Language.EN.as_data(): "Sent anonymously!\n\nWe recommend that you regularly delete any sensitive messages - the bot cannot do this for you.",
                                        }
                                        if anonymize_users
                                        else {
                                            Language.RU.as_data(): "Отправлено!",
                                            Language.EN.as_data(): "Sent!",
                                        }
                                    )[admin_lang],
                                    throttling={
                                        Language.RU.as_data(): "Не присылайте больше {} сообщений в минуту!",
                                        Language.EN.as_data(): "Do not send more than {} messages per minute!",
                                    }[admin_lang],
                                ),
                                messages_to_admin=MessagesToAdmin(
                                    copied_to_user_ok={
                                        Language.RU.as_data(): "Передано!",
                                        Language.EN.as_data(): "Sent!",
                                    }[admin_lang],
                                    deleted_message_ok={
                                        Language.RU.as_data(): "Сообщение удалено!",
                                        Language.EN.as_data(): "Message deleted!",
                                    }[admin_lang],
                                    can_not_delete_message={
                                        Language.RU.as_data(): "Не получилось удалить сообщение!",
                                        Language.EN.as_data(): "Failed to delete the message!",
                                    }[admin_lang],
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
                version_message="initial version created with baw bot",
                start=True,
                display_name=bot_name,
            ),
        ):
            await bot.send_message(
                user.id,
                {
                    Language.RU.as_data(): "Не получилось создать бота...",
                    Language.EN.as_data(): "Failed to create bot...",
                }[admin_lang],
            )
            return
        await bot.send_message(
            user.id,
            {
                Language.RU.as_data(): f'Браво! Ваш бот запущен – проверьте его! Для этого перейдите в @{bot_username}, нажмите "start" и напишите любое сообщение в чат.',
                Language.EN.as_data(): f'Bravo! Your bot is up and running – now it\' time to test it! Go to @{bot_username}, click "start" and write any message to the chat.',
            }[admin_lang],
        )
        await asyncio.sleep(0.15)
        studio_link = api.config.base_url.strip("/") + f"/studio/{moduli_bot_id}"
        await bot.send_message(
            user.id,
            {
                Language.RU.as_data(): f"Сообщения от пользователей будут приходить в чат с @{bot_username}. Ответы (по свайпу влево или двойному нажатию на сообщения) будут отправлены от лица бота.\n\nВ {html_link(href=studio_link, text='веб-версии moduli')} можно подключить админ-чат, где на сообщения смогут отвечать несколько человек. Там же доступно редактирование бота и более сложные сценарии использования.",
                Language.EN.as_data(): f"Messages from users will be sent to your chat with @{bot_username}. Replies (upon left swipe or double-tap on a message) will be sent by the bot.\n\nIn {html_link(href=studio_link, text='moduli')} you can connect an admin chat, where several people can reply to messages. There you can also edit the bot and add more complex usage scenarios.",
            }[admin_lang],
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        if after is not None:
            await after(user)

    async def cancel_form(context: FormExitContext) -> None:
        user = context.last_update.from_user
        admin_lang = await language_store.get_user_language(user)
        await bot.send_message(
            chat_id=user.id,
            text={
                Language.RU.as_data(): "Вы можете всегда вернуться к созданию бота!",
                Language.EN.as_data(): "You can always get back to creating a bot!",
            }[admin_lang],
        )
        if after is not None:
            await after(user)

    form_handler.setup(bot, on_form_completed=complete_form, on_form_cancelled=cancel_form)

    return form_handler


if __name__ == "__main__":
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
                config=TrustedModuliApiClientConfig(
                    base_url=os.environ["MODULI_API_URL"],
                    trusted_client_token=os.environ["MODULI_API_TOKEN"],
                ),
            )
            await api.ping()

            language_store = LanguageStore(
                redis=redis,
                bot_prefix=bot_prefix,
                supported_languages=[Language.EN, Language.RU],
                default_language=Language.EN,
                menu_config=LanguageSelectionMenuConfig(
                    emojj_buttons=False,
                    prompt={lang: "Select language / выберите язык" for lang in (Language.RU, Language.EN)},
                ),
            )

            form_handler = moduli_bot_form_handler(
                bot,
                bot_prefix=bot_prefix,
                redis=redis,
                api=api,
                language_store=language_store,
            )

            @bot.message_handler(commands=["start"])
            async def start_form(m: tg.Message) -> None:
                await form_handler.start(
                    bot,
                    m.from_user,
                    dynamic_data=api.config,
                )

            runner = BotRunner(bot_prefix=bot_prefix, bot=bot)
            await runner.run_polling()

    asyncio.run(main())
