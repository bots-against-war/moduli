import pytest
from pydantic import ValidationError
from telebot.test_util import MockedAsyncTeleBot
from telebot_components.redis_utils.emulation import RedisEmulation

from telebot_constructor.bot_config import (
    BotConfig,
    UserFlowBlockConfig,
    UserFlowConfig,
    UserFlowEntryPointConfig,
)
from telebot_constructor.construct import construct_bot
from telebot_constructor.user_flow.blocks.content import ContentBlock
from telebot_constructor.user_flow.blocks.human_operator import (
    FeedbackHandlerConfig,
    HumanOperatorBlock,
    MessagesToAdmin,
    MessagesToUser,
)
from telebot_constructor.user_flow.blocks.language_select import (
    LanguageSelectBlock,
    LanguageSelectionMenuConfig,
)
from telebot_constructor.user_flow.entrypoints.catch_all import CatchAllEntryPoint
from telebot_constructor.user_flow.entrypoints.command import CommandEntryPoint
from telebot_constructor.user_flow.entrypoints.regex_match import RegexMatchEntryPoint
from telebot_constructor.utils.pydantic import Language
from tests.utils import (
    assert_method_call_kwargs_include,
    dummy_errors_store,
    dummy_form_results_store,
    dummy_secret_store,
    tg_update_message_to_bot,
)


def test_user_flow_config_model_validation() -> None:
    with pytest.raises(ValueError, match=r".*?All block ids must be unique, but there are duplicates: 1"):
        UserFlowConfig(
            entrypoints=[],
            blocks=[
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(block_id="1", message_text="one", next_block_id=None),
                ),
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(block_id="1", message_text="also one", next_block_id=None),
                ),
            ],
            node_display_coords={},
        )


async def test_simple_user_flow() -> None:
    bot_config = BotConfig(
        token_secret_name="token",
        display_name="Test bot",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(
                        entrypoint_id="command-1",
                        command="hello",
                        next_block_id="message-1",
                        short_description="example command",
                    ),
                )
            ],
            blocks=[
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="message-1",
                        message_text="hello!",
                        next_block_id="message-2",
                    ),
                ),
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="message-2",
                        message_text="how are you today?",
                        next_block_id=None,
                    ),
                ),
            ],
            node_display_coords={},
        ),
    )

    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)
    username = "user123"
    await secret_store.save_secret(secret_name="token", secret_value="mock-token", owner_id=username)
    bot_runner = await construct_bot(
        owner_id=username,
        bot_id="simple-user-flow-bot",
        bot_config=bot_config,
        form_results_store=dummy_form_results_store(),
        errors_store=dummy_errors_store(),
        secret_store=secret_store,
        redis=redis,
        owner_chat_id=0,
        _bot_factory=MockedAsyncTeleBot,
    )
    assert not bot_runner.background_jobs
    assert not bot_runner.aux_endpoints

    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)

    # checking construct-time calls
    assert len(bot.method_calls["set_my_commands"]) == 1
    bot_commands = bot.method_calls["set_my_commands"][0].full_kwargs["commands"]
    assert len(bot_commands) == 1
    assert bot_commands[0].to_json() == '{"command":"hello","description":"example command"}'
    bot.method_calls.clear()

    # user interaction
    await bot.process_new_updates([tg_update_message_to_bot(1312, first_name="User", text="/hello")])
    assert len(bot.method_calls) == 1
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"],
        [
            {"chat_id": 1312, "text": "hello!"},
            {"chat_id": 1312, "text": "how are you today?"},
        ],
    )


@pytest.mark.parametrize("catch_all", [True, False])
async def test_flow_with_human_operator(catch_all: bool) -> None:
    ADMIN_CHAT_ID = 98765
    USER_ID = 1312
    bot_config = BotConfig(
        token_secret_name="token",
        display_name="Simple feedback bot",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(
                        entrypoint_id="command-1",
                        command="start",
                        next_block_id="message-1",
                    ),
                )
            ],
            blocks=[
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="message-1",
                        message_text="Hi, I'm a bot",
                        next_block_id="human-operator-1",
                    ),
                ),
                UserFlowBlockConfig(
                    human_operator=HumanOperatorBlock(
                        block_id="human-operator-1",
                        catch_all=catch_all,
                        feedback_handler_config=FeedbackHandlerConfig(
                            admin_chat_id=ADMIN_CHAT_ID,
                            forum_topic_per_user=False,
                            messages_to_user=MessagesToUser(forwarded_to_admin_ok="ok", throttling=""),
                            messages_to_admin=MessagesToAdmin(
                                copied_to_user_ok="copied ok", deleted_message_ok="", can_not_delete_message=""
                            ),
                            anonimyze_users=False,
                            max_messages_per_minute=10,
                            hashtags_in_admin_chat=True,
                            unanswered_hashtag="unanswered",
                            hashtag_message_rarer_than=None,
                            message_log_to_admin_chat=True,
                        ),
                    ),
                ),
            ],
            node_display_coords={},
        ),
    )

    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)
    username = "user123"
    await secret_store.save_secret(secret_name="token", secret_value="mock-token", owner_id=username)
    bot_runner = await construct_bot(
        owner_id=username,
        bot_id=f"flow-with-human-operator-bot-{catch_all=}",
        bot_config=bot_config,
        form_results_store=dummy_form_results_store(),
        errors_store=dummy_errors_store(),
        secret_store=secret_store,
        redis=redis,
        owner_chat_id=0,
        _bot_factory=MockedAsyncTeleBot,
    )

    assert not bot_runner.background_jobs
    assert not bot_runner.aux_endpoints

    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)

    assert len(bot.method_calls["set_my_commands"]) == 1
    bot_commands = bot.method_calls["set_my_commands"][0].full_kwargs["commands"]
    assert len(bot_commands) == 4
    # too much hassle to compare the actual command values...
    # assert bot_commands[0].to_json() == '{"command":"undo","description":"...???"}'

    bot.method_calls.clear()  # remove construct-time calls

    # direct message to bot but not a command
    await bot.process_new_updates([tg_update_message_to_bot(USER_ID, first_name="User", text="hello i am user")])
    if catch_all:
        assert_method_call_kwargs_include(
            bot.method_calls["send_message"],
            [
                {"chat_id": ADMIN_CHAT_ID, "text": "#unanswered"},  # hashtag in admin chat
                {
                    "chat_id": ADMIN_CHAT_ID,
                    "text": '<a href="tg://user?id=1312">User (#1312)</a>',
                    "parse_mode": "HTML",
                },  # user identifier in admin chat
                {"chat_id": USER_ID, "text": "ok"},  # reply to user
            ],
        )
        assert_method_call_kwargs_include(
            bot.method_calls["copy_message"],
            [
                {"chat_id": ADMIN_CHAT_ID, "from_chat_id": USER_ID},
            ],
        )
    else:
        # no response, human operator block is not active
        assert len(bot.method_calls) == 0
    bot.method_calls.clear()

    # /start command
    await bot.process_new_updates([tg_update_message_to_bot(USER_ID, first_name="User", text="/start")])
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"],
        [
            {"chat_id": USER_ID, "text": "Hi, I'm a bot"},
        ],
    )
    bot.method_calls.clear()

    # message to bot after the command
    await bot.process_new_updates([tg_update_message_to_bot(USER_ID, first_name="User", text="hello i am user")])
    if catch_all:
        assert_method_call_kwargs_include(
            bot.method_calls["send_message"],
            [
                {"chat_id": USER_ID, "text": "ok"},  # reply to user
            ],
        )
    else:
        assert_method_call_kwargs_include(
            bot.method_calls["send_message"],
            [
                {"chat_id": ADMIN_CHAT_ID, "text": "#unanswered"},  # hashtag in admin chat
                {
                    "chat_id": ADMIN_CHAT_ID,
                    "text": '<a href="tg://user?id=1312">User (#1312)</a>',
                    "parse_mode": "HTML",
                },  # user identifier in admin chat
                {"chat_id": USER_ID, "text": "ok"},  # reply to user
            ],
        )

    assert_method_call_kwargs_include(
        bot.method_calls["copy_message"],
        [
            {"chat_id": ADMIN_CHAT_ID, "from_chat_id": USER_ID},
        ],
    )


async def test_catch_all_entrypoint() -> None:
    USER_ID = 1312
    bot_config = BotConfig(
        token_secret_name="token",
        display_name="",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(entrypoint_id="command", command="cmd", next_block_id="message-1"),
                ),
                UserFlowEntryPointConfig(
                    catch_all=CatchAllEntryPoint(entrypoint_id="catch-all", next_block_id="message-2")
                ),
            ],
            blocks=[
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="message-1", message_text="Message 1", next_block_id=None
                    ),
                ),
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="message-2", message_text="Message 2", next_block_id=None
                    ),
                ),
            ],
            node_display_coords={},
        ),
    )

    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)
    username = "user123"
    await secret_store.save_secret(secret_name="token", secret_value="mock-token", owner_id=username)
    bot_runner = await construct_bot(
        owner_id=username,
        bot_id="catch-all-entrypoint-bot",
        bot_config=bot_config,
        form_results_store=dummy_form_results_store(),
        errors_store=dummy_errors_store(),
        secret_store=secret_store,
        redis=redis,
        owner_chat_id=0,
        _bot_factory=MockedAsyncTeleBot,
    )

    assert not bot_runner.background_jobs
    assert not bot_runner.aux_endpoints

    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)
    bot.method_calls.clear()  # remove construct-time calls

    # command
    await bot.process_new_updates([tg_update_message_to_bot(USER_ID, first_name="User", text="/cmd")])
    assert_method_call_kwargs_include(bot.method_calls["send_message"], [{"chat_id": USER_ID, "text": "Message 1"}])
    bot.method_calls.clear()

    # any other message for catch-all entrypoint
    await bot.process_new_updates([tg_update_message_to_bot(USER_ID, first_name="User", text="HIIIIIIII!!!!!")])
    assert_method_call_kwargs_include(bot.method_calls["send_message"], [{"chat_id": USER_ID, "text": "Message 2"}])
    bot.method_calls.clear()


async def test_regex_match_entrypoint() -> None:
    USER_ID = 1312
    bot_config = BotConfig(
        token_secret_name="token",
        display_name="",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    regex=RegexMatchEntryPoint(
                        entrypoint_id="regex-1", regex="literal value", next_block_id="message-literal"
                    )
                ),
                UserFlowEntryPointConfig(
                    regex=RegexMatchEntryPoint(entrypoint_id="regex-2", regex=".+", next_block_id="message-non-empty")
                ),
                UserFlowEntryPointConfig(
                    regex=RegexMatchEntryPoint(entrypoint_id="regex-3", regex="^$", next_block_id="message-empty")
                ),
            ],
            blocks=[
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="message-literal", message_text="Literal value", next_block_id=None
                    ),
                ),
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="message-non-empty", message_text="Non-empty", next_block_id=None
                    ),
                ),
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="message-empty", message_text="Empty", next_block_id=None
                    ),
                ),
            ],
            node_display_coords={},
        ),
    )

    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)
    username = "user123"
    await secret_store.save_secret(secret_name="token", secret_value="mock-token", owner_id=username)
    bot_runner = await construct_bot(
        owner_id=username,
        bot_id="regex-entrypoint-bot",
        bot_config=bot_config,
        form_results_store=dummy_form_results_store(),
        errors_store=dummy_errors_store(),
        secret_store=secret_store,
        redis=redis,
        owner_chat_id=0,
        _bot_factory=MockedAsyncTeleBot,
    )

    assert not bot_runner.background_jobs
    assert not bot_runner.aux_endpoints

    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)
    bot.method_calls.clear()  # remove construct-time calls

    await bot.process_new_updates([tg_update_message_to_bot(USER_ID, first_name="User", text="")])
    assert_method_call_kwargs_include(bot.method_calls["send_message"], [{"chat_id": USER_ID, "text": "Empty"}])
    bot.method_calls.clear()

    await bot.process_new_updates(
        [tg_update_message_to_bot(USER_ID, first_name="User", text="message containing literal value!!!")]
    )
    assert_method_call_kwargs_include(bot.method_calls["send_message"], [{"chat_id": USER_ID, "text": "Literal value"}])
    bot.method_calls.clear()

    await bot.process_new_updates([tg_update_message_to_bot(USER_ID, first_name="User", text="aaaabbbb")])
    assert_method_call_kwargs_include(bot.method_calls["send_message"], [{"chat_id": USER_ID, "text": "Non-empty"}])
    bot.method_calls.clear()


async def test_forbid_multiple_catch_all() -> None:
    with pytest.raises(ValidationError, match=".*At most one catch-all block/entrypoint is allowed, but found:"):
        BotConfig(
            token_secret_name="foobar",
            display_name="barfoo",
            user_flow_config=UserFlowConfig(
                entrypoints=[
                    UserFlowEntryPointConfig(
                        regex=RegexMatchEntryPoint(entrypoint_id="regex-catch-all", regex=".*", next_block_id=None)
                    ),
                    UserFlowEntryPointConfig(
                        catch_all=CatchAllEntryPoint(entrypoint_id="catch-all", next_block_id=None)
                    ),
                ],
                blocks=[],
                node_display_coords={},
            ),
        )

    with pytest.raises(ValidationError, match=".*At most one catch-all block/entrypoint is allowed, but found:"):
        BotConfig(
            token_secret_name="foobar",
            display_name="barfoo",
            user_flow_config=UserFlowConfig(
                entrypoints=[
                    UserFlowEntryPointConfig(
                        catch_all=CatchAllEntryPoint(entrypoint_id="catch-all", next_block_id=None)
                    ),
                ],
                blocks=[
                    UserFlowBlockConfig(
                        human_operator=HumanOperatorBlock(
                            block_id="human-op",
                            catch_all=True,
                            feedback_handler_config=FeedbackHandlerConfig(
                                admin_chat_id=12345,
                                forum_topic_per_user=False,
                                messages_to_user=MessagesToUser(forwarded_to_admin_ok="ok", throttling=""),
                                messages_to_admin=MessagesToAdmin(
                                    copied_to_user_ok="copied ok", deleted_message_ok="", can_not_delete_message=""
                                ),
                                anonimyze_users=False,
                                max_messages_per_minute=10,
                                hashtags_in_admin_chat=True,
                                unanswered_hashtag="unanswered",
                                hashtag_message_rarer_than=None,
                                message_log_to_admin_chat=True,
                            ),
                        )
                    )
                ],
                node_display_coords={},
            ),
        )


async def test_multilang_user_flow() -> None:
    bot_config = BotConfig(
        token_secret_name="token",
        display_name="Test bot",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(
                        entrypoint_id="start-command",
                        command="start",
                        next_block_id="hello-message",
                    ),
                ),
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(
                        entrypoint_id="language-command",
                        command="language",
                        next_block_id="language-select",
                    ),
                ),
            ],
            blocks=[
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="hello-message",
                        message_text={Language.lookup("en"): "hello user", Language.lookup("ru"): "привет юзер"},
                        next_block_id=None,
                    ),
                ),
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="language-selected-message",
                        message_text={
                            Language.lookup("en"): "thanks for selecting the english language",
                            Language.lookup("ru"): "спасибо что выбрали русский язык",
                        },
                        next_block_id=None,
                    ),
                ),
                UserFlowBlockConfig(
                    language_select=LanguageSelectBlock(
                        block_id="language-select",
                        menu_config=LanguageSelectionMenuConfig(
                            propmt={Language.lookup("en"): "choose language", Language.lookup("ru"): "выберите язык"},
                            is_blocking=True,
                            emoji_buttons=True,
                        ),
                        supported_languages=[Language.lookup("en"), Language.lookup("ru")],
                        default_language=Language.lookup("en"),
                        language_selected_next_block_id="language-selected-message",
                    )
                ),
            ],
            node_display_coords={},
        ),
    )

    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)
    username = "bot-admin-1312"
    await secret_store.save_secret(secret_name="token", secret_value="mock-token", owner_id=username)
    bot_runner = await construct_bot(
        owner_id=username,
        bot_id="simple-user-flow-bot",
        bot_config=bot_config,
        form_results_store=dummy_form_results_store(),
        errors_store=dummy_errors_store(),
        secret_store=secret_store,
        redis=redis,
        owner_chat_id=0,
        _bot_factory=MockedAsyncTeleBot,
    )
    assert not bot_runner.background_jobs
    assert not bot_runner.aux_endpoints

    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)
    bot.method_calls.clear()

    # using start command to see hello in the default language
    await bot.process_new_updates([tg_update_message_to_bot(161, first_name="User", text="/start")])
    assert len(bot.method_calls) == 1
    assert_method_call_kwargs_include(bot.method_calls["send_message"], [{"text": "hello user", "chat_id": 161}])
    bot.method_calls.clear()

    # using language selection menu
    await bot.process_new_updates([tg_update_message_to_bot(161, first_name="User", text="/language")])
    assert len(bot.method_calls) == 1
    assert_method_call_kwargs_include(bot.method_calls["send_message"], [{"chat_id": 161, "text": "choose language"}])
    assert bot.method_calls["send_message"][0].full_kwargs["reply_markup"].to_dict() == {
        "keyboard": [[{"text": "🇬🇧 English"}], [{"text": "🇷🇺 Русский"}]],
        "one_time_keyboard": True,
        "resize_keyboard": True,
    }
    bot.method_calls.clear()

    await bot.process_new_updates([tg_update_message_to_bot(161, first_name="User", text="🇷🇺 Русский")])
    assert len(bot.method_calls) == 1
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"], [{"chat_id": 161, "text": "спасибо что выбрали русский язык"}]
    )
    bot.method_calls.clear()

    # using start command again, now in the selected language
    await bot.process_new_updates([tg_update_message_to_bot(161, first_name="User", text="/start")])
    assert len(bot.method_calls) == 1
    assert_method_call_kwargs_include(bot.method_calls["send_message"], [{"text": "привет юзер", "chat_id": 161}])
    bot.method_calls.clear()


async def test_no_infinte_loop_flow() -> None:
    bot_config = BotConfig(
        token_secret_name="token",
        display_name="Test bot",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(
                        entrypoint_id="command-1",
                        command="hello",
                        next_block_id="message-1",
                        short_description="example command",
                    ),
                )
            ],
            blocks=[
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="message-1",
                        message_text="hello!",
                        next_block_id="message-2",
                    ),
                ),
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="message-2",
                        message_text="how are you today?",
                        next_block_id="message-1",
                    ),
                ),
            ],
            node_display_coords={},
        ),
    )

    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)
    username = "user123"
    await secret_store.save_secret(secret_name="token", secret_value="mock-token", owner_id=username)
    bot_runner = await construct_bot(
        owner_id=username,
        bot_id="simple-user-flow-bot",
        bot_config=bot_config,
        form_results_store=dummy_form_results_store(),
        errors_store=dummy_errors_store(),
        secret_store=secret_store,
        redis=redis,
        owner_chat_id=0,
        _bot_factory=MockedAsyncTeleBot,
    )
    assert not bot_runner.background_jobs
    assert not bot_runner.aux_endpoints

    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)

    await bot.process_new_updates([tg_update_message_to_bot(1312, first_name="User", text="/hello")])

    assert len(bot.method_calls) == 3
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"],
        [
            {"chat_id": 1312, "text": "hello!"},
            {"chat_id": 1312, "text": "how are you today?"},
        ],
    )
