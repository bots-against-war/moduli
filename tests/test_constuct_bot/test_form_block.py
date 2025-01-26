from typing import Any

import pytest
from telebot.test_util import MockedAsyncTeleBot
from telebot_components.redis_utils.emulation import RedisEmulation

from telebot_constructor.bot_config import (
    BotConfig,
    UserFlowBlockConfig,
    UserFlowConfig,
    UserFlowEntryPointConfig,
)
from telebot_constructor.construct import construct_bot
from telebot_constructor.store.form_results import (
    FormResultsFilter,
    FormResultsStore,
    GlobalFormId,
)
from telebot_constructor.user_flow.blocks.content import ContentBlock
from telebot_constructor.user_flow.blocks.form import (
    BranchingFormMemberConfig,
    EnumOption,
    FormBlock,
    FormBranchConfig,
    FormFieldConfig,
    FormMessages,
    FormResultsExport,
    FormResultsExportToChatConfig,
    FormResultUserAttribution,
    PlainTextFormFieldConfig,
    SingleSelectFormFieldConfig,
)
from telebot_constructor.user_flow.entrypoints.command import CommandEntryPoint
from tests.utils import (
    RECENT_TIMESTAMP,
    assert_method_call_dictified_kwargs_include,
    assert_method_call_kwargs_include,
    dummy_errors_store,
    dummy_form_results_store,
    dummy_secret_store,
    mask_recent_timestamps,
    tg_update_message_to_bot,
)


@pytest.mark.parametrize(
    "form_result_export_kwargs, expected_name_line",
    [
        pytest.param(
            dict(is_anonymous=False),
            '<a href="tg://user?id=161">User</a>\n\n',
            id="legacy way of specifying user attribution by flag = true",
        ),
        pytest.param(
            dict(is_anonymous=True),
            "",
            id="legacy way of specifying user attribution by flag = false",
        ),
        pytest.param(
            dict(user_attribution=FormResultUserAttribution.FULL),
            '<a href="tg://user?id=161">User</a>\n\n',
            id="full user attribution",
        ),
        pytest.param(
            dict(user_attribution=FormResultUserAttribution.NAME),
            "User\n\n",
            id="name-only user attribution",
        ),
        pytest.param(
            dict(user_attribution=FormResultUserAttribution.UNIQUE_ID),
            "🤯🧄🌝🎳🚿♿\n\n",
            id="anonymized id user attribution",
        ),
        pytest.param(
            dict(user_attribution=FormResultUserAttribution.NONE),
            "",
            id="no user attribution",
        ),
    ],
)
async def test_user_flow_with_form(
    form_result_export_kwargs: dict[str, Any],
    expected_name_line: str,
) -> None:
    bot_config = BotConfig(
        token_secret_name="token",
        display_name="lalala",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(
                        entrypoint_id="start-cmd",
                        command="start",
                        next_block_id="hello-msg",
                    ),
                ),
            ],
            blocks=[
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="hello-msg",
                        message_text="hi i'm form bot",
                        next_block_id="form",
                    ),
                ),
                UserFlowBlockConfig(
                    content=ContentBlock.simple_text(
                        block_id="thanks-msg",
                        message_text="thanks for using the bot",
                        next_block_id=None,
                    ),
                ),
                UserFlowBlockConfig(
                    form=FormBlock(
                        block_id="form",
                        form_name="test-form",
                        members=[
                            BranchingFormMemberConfig(
                                field=FormFieldConfig(
                                    plain_text=PlainTextFormFieldConfig(
                                        id="name",
                                        name="Name",
                                        prompt="what is your name?",
                                        is_long_text=False,
                                        is_required=True,
                                        result_formatting="auto",
                                        empty_text_error_msg="please provide an answer",
                                    ),
                                )
                            ),
                            BranchingFormMemberConfig(
                                field=FormFieldConfig(
                                    single_select=SingleSelectFormFieldConfig(
                                        id="does_like_apples",
                                        name="Apples",
                                        prompt="do you like apples?",
                                        is_required=True,
                                        result_formatting="auto",
                                        options=[
                                            EnumOption(id="yes", label="Yes I do"),
                                            EnumOption(id="no", label="No!!!"),
                                        ],
                                        invalid_enum_error_msg="please use reply keyboard buttons",
                                    ),
                                )
                            ),
                            BranchingFormMemberConfig(
                                branch=FormBranchConfig(
                                    members=[
                                        BranchingFormMemberConfig(
                                            field=FormFieldConfig(
                                                plain_text=PlainTextFormFieldConfig(
                                                    id="which_apples",
                                                    name="Which apples",
                                                    prompt="which apples do you like?",
                                                    is_required=True,
                                                    is_long_text=False,
                                                    result_formatting="auto",
                                                    empty_text_error_msg="please answer the question",
                                                )
                                            )
                                        )
                                    ],
                                    condition_match_value="yes",
                                )
                            ),
                        ],
                        messages=FormMessages(
                            form_start="hi please fill out the form!",
                            cancel_command_is="{} - cancel filling",
                            field_is_skippable="skip field - {}",
                            field_is_not_skippable="field is not skippable",
                            please_enter_correct_value="please enter corrected value",
                            unsupported_command="the only supported commands are: {}",
                        ),
                        results_export=FormResultsExport(
                            echo_to_user=True,
                            to_chat=FormResultsExportToChatConfig(chat_id=111222, via_feedback_handler=True),
                            **form_result_export_kwargs,
                        ),
                        form_completed_next_block_id="thanks-msg",
                        form_cancelled_next_block_id=None,
                    ),
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
        bot_id="form-bot-test",
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

    # using start command to start the form
    await bot.process_new_updates([tg_update_message_to_bot(161, first_name="User", text="/start")])
    assert len(bot.method_calls) == 1
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"],
        [
            {"text": "hi i'm form bot", "chat_id": 161},
            {"chat_id": 161, "text": "hi please fill out the form!\n\n/cancel - cancel filling"},
            {"chat_id": 161, "text": "what is your name?"},
        ],
    )
    assert_method_call_dictified_kwargs_include(bot.method_calls["send_message"], [{}, {}, {}])
    bot.method_calls.clear()

    await bot.process_new_updates([tg_update_message_to_bot(161, first_name="User", text="John Doe")])
    assert len(bot.method_calls) == 1
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"],
        [
            {"chat_id": 161, "text": "do you like apples?"},
        ],
    )
    assert_method_call_dictified_kwargs_include(
        bot.method_calls["send_message"],
        [
            {
                "reply_markup": {
                    "keyboard": [[{"text": "Yes I do"}, {"text": "No!!!"}]],
                    "one_time_keyboard": True,
                    "resize_keyboard": True,
                },
            }
        ],
    )
    bot.method_calls.clear()

    await bot.process_new_updates([tg_update_message_to_bot(161, first_name="User", text="Yes I do")])
    assert len(bot.method_calls) == 1
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"],
        [
            {"chat_id": 161, "text": "which apples do you like?"},
        ],
    )
    bot.method_calls.clear()

    await bot.process_new_updates([tg_update_message_to_bot(161, first_name="User", text="granny smith")])
    assert len(bot.method_calls) == 1
    assert_method_call_kwargs_include(
        bot.method_calls["send_message"],
        [
            {
                "chat_id": 161,
                "text": ("<b>Name</b>: John Doe\n" + "<b>Apples</b>: Yes I do\n" + "<b>Which apples</b>: granny smith"),
                "parse_mode": "HTML",
            },
            {
                "chat_id": 111222,
                "text": (
                    expected_name_line
                    + "<b>Name</b>: John Doe\n"
                    + "<b>Apples</b>: Yes I do\n"
                    + "<b>Which apples</b>: granny smith"
                ),
                "parse_mode": "HTML",
            },
            {"text": "thanks for using the bot", "chat_id": 161},
        ],
    )
    bot.method_calls.clear()


async def test_form_results_internal_storage() -> None:
    bot_config = BotConfig(
        token_secret_name="token",
        display_name="unused",
        user_flow_config=UserFlowConfig(
            entrypoints=[
                UserFlowEntryPointConfig(
                    command=CommandEntryPoint(
                        entrypoint_id="start-cmd",
                        command="start",
                        next_block_id="form",
                    ),
                ),
            ],
            blocks=[
                UserFlowBlockConfig(
                    form=FormBlock(
                        block_id="form",
                        form_name="test-form",
                        members=[
                            BranchingFormMemberConfig(
                                field=FormFieldConfig(
                                    plain_text=PlainTextFormFieldConfig(
                                        id="age",
                                        name="Age",
                                        prompt="what is your age?",
                                        is_long_text=False,
                                        is_required=True,
                                        result_formatting="auto",
                                        empty_text_error_msg="please provide an answer",
                                    ),
                                )
                            ),
                            BranchingFormMemberConfig(
                                field=FormFieldConfig(
                                    plain_text=PlainTextFormFieldConfig(
                                        id="dog_name",
                                        name="Dog's name",
                                        prompt="What's your dog's name?",
                                        is_long_text=False,
                                        is_required=True,
                                        result_formatting="auto",
                                        empty_text_error_msg="please provide an answer",
                                    ),
                                )
                            ),
                        ],
                        messages=FormMessages(
                            form_start="hello welcome to the form",
                            cancel_command_is="{} - cancel filling",
                            field_is_skippable="skip field - {}",
                            field_is_not_skippable="field is not skippable",
                            please_enter_correct_value="please enter corrected value",
                            unsupported_command="the only supported commands are: {}",
                        ),
                        results_export=FormResultsExport(
                            user_attribution=FormResultUserAttribution.FULL,
                            echo_to_user=False,
                            to_chat=None,
                            to_store=True,
                        ),
                        form_completed_next_block_id=None,
                        form_cancelled_next_block_id=None,
                    ),
                ),
            ],
            node_display_coords={},
        ),
    )
    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)
    username = "botauthor"
    bot_id = "form-results-storage-test-bot"
    form_results_store = FormResultsStore(redis)
    await secret_store.save_secret(secret_name="token", secret_value="mock-token", owner_id=username)
    bot_runner = await construct_bot(
        owner_id=username,
        bot_id=bot_id,
        bot_config=bot_config,
        form_results_store=form_results_store.adapter_for(owner_id=username, bot_id=bot_id),
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

    # several users fill the form
    for user_id, first_name, user_username in [
        (1, "Alice", "all"),
        (2, "Bob", "bob"),
        (3, "Mary", "mmmmmm"),
    ]:
        user_kw = {"username": user_username}
        # using start command to start the form
        await bot.process_new_updates(
            [tg_update_message_to_bot(user_id, first_name=first_name, text="/start", user_kwargs=user_kw)]
        )
        assert len(bot.method_calls) == 1
        assert_method_call_kwargs_include(
            bot.method_calls["send_message"],
            [
                {"chat_id": user_id, "text": "hello welcome to the form\n\n/cancel - cancel filling"},
                {"chat_id": user_id, "text": "what is your age?"},
            ],
        )
        assert_method_call_dictified_kwargs_include(bot.method_calls["send_message"], [{}, {}])
        bot.method_calls.clear()

        await bot.process_new_updates(
            [
                tg_update_message_to_bot(
                    user_id, first_name=first_name, text=f"I'm {user_id + 25} y.o.", user_kwargs=user_kw
                )
            ]
        )
        assert len(bot.method_calls) == 1
        assert_method_call_kwargs_include(
            bot.method_calls["send_message"],
            [
                {"chat_id": user_id, "text": "What's your dog's name?"},
            ],
        )
        assert_method_call_dictified_kwargs_include(bot.method_calls["send_message"], [{}])
        bot.method_calls.clear()

        await bot.process_new_updates(
            [
                tg_update_message_to_bot(
                    user_id, first_name=first_name, text=f"My dog is called {first_name} after me", user_kwargs=user_kw
                )
            ]
        )
        assert len(bot.method_calls) == 0

    # check the result is saved
    assert mask_recent_timestamps(
        await form_results_store.load_page(
            form_id=GlobalFormId(owner_id=username, bot_id=bot_id, form_block_id="form"),
            offset=0,
            count=2,
        )
    ) == [
        {
            "timestamp": RECENT_TIMESTAMP,
            "age": "I'm 27 y.o.",
            "dog_name": "My dog is called Bob after me",
            "user": "Bob (@bob, #2)",
        },
        {
            "timestamp": RECENT_TIMESTAMP,
            "age": "I'm 28 y.o.",
            "dog_name": "My dog is called Mary after me",
            "user": "Mary (@mmmmmm, #3)",
        },
    ]
    all_results, is_full = await form_results_store.load(
        form_id=GlobalFormId(owner_id=username, bot_id=bot_id, form_block_id="form"),
        filter=FormResultsFilter(min_timestamp=None, max_timestamp=None),
    )
    assert is_full
    assert mask_recent_timestamps(all_results) == [
        {
            "timestamp": RECENT_TIMESTAMP,
            "user": "Alice (@all, #1)",
            "age": "I'm 26 y.o.",
            "dog_name": "My dog is called Alice after me",
        },
        {
            "timestamp": RECENT_TIMESTAMP,
            "user": "Bob (@bob, #2)",
            "age": "I'm 27 y.o.",
            "dog_name": "My dog is called Bob after me",
        },
        {
            "timestamp": RECENT_TIMESTAMP,
            "user": "Mary (@mmmmmm, #3)",
            "age": "I'm 28 y.o.",
            "dog_name": "My dog is called Mary after me",
        },
    ]
