import datetime
from typing import Tuple

import aiohttp.web
from pytest_aiohttp.plugin import AiohttpClient  # type: ignore
from telebot.test_util import MockedAsyncTeleBot

from telebot_constructor.app import ModuliApp
from tests.test_app.conftest import MockBotRunner
from tests.utils import (
    RECENT_TIMESTAMP,
    assert_method_call_kwargs_include,
    mask_recent_timestamps,
    tg_update_message_to_bot,
)


async def test_form_results_api(
    constructor_app: Tuple[ModuliApp, aiohttp.web.Application],
    aiohttp_client: AiohttpClient,
) -> None:
    constructor, web_app = constructor_app
    client = await aiohttp_client(web_app)

    # saving a token
    resp = await client.post("/api/secrets/test-token", data="aaaaaa")
    assert resp.status == 200

    # saving a bot config
    resp = await client.post(
        "/api/config/mybot",
        json={
            "config": {
                "token_secret_name": "test-token",
                "user_flow_config": {
                    "entrypoints": [
                        {
                            "command": {
                                "entrypoint_id": "default-start-command",
                                "command": "start",
                                "next_block_id": "form-block-123",
                            },
                        }
                    ],
                    "blocks": [
                        {
                            "form": {
                                "block_id": "form-block-123",
                                "form_name": "super-form-testing-1-2",
                                "members": [
                                    {
                                        "field": {
                                            "plain_text": {
                                                "id": "form-field-1",
                                                "name": "one",
                                                "prompt": "Please answer the first question",
                                                "is_required": True,
                                                "result_formatting": "auto",
                                                "is_long_text": False,
                                                "empty_text_error_msg": "Error: empty answer",
                                            },
                                        },
                                    },
                                    {
                                        "field": {
                                            "plain_text": {
                                                "id": "form-field-2",
                                                "name": "two",
                                                "prompt": "Please answer the second question",
                                                "is_required": True,
                                                "result_formatting": "auto",
                                                "is_long_text": False,
                                                "empty_text_error_msg": "Error: empty answer",
                                            },
                                        },
                                    },
                                ],
                                "messages": {
                                    "form_start": "Hello welcome to the form testing bot",
                                    "cancel_command_is": "/cancel — to cancel",
                                    "field_is_skippable": "/skip — to skip",
                                    "field_is_not_skippable": "Field isn't skippable",
                                    "please_enter_correct_value": "Fix the value pls",
                                    "unsupported_command": "Bad cmd, get out",
                                },
                                "results_export": {
                                    "user_attribution": "name",
                                    "echo_to_user": True,
                                    "to_chat": None,
                                    "to_store": True,
                                },
                                "form_completed_next_block_id": None,
                                "form_cancelled_next_block_id": None,
                            },
                        },
                    ],
                    "node_display_coords": {},
                },
            },
            "display_name": "my test bot",
            "start": True,
            "version_message": "init",
        },
    )
    assert resp.status == 201

    resp = await client.get("/api/info/mybot")
    assert resp.status == 200
    assert mask_recent_timestamps(await resp.json()) == {
        "bot_id": "mybot",
        "display_name": "my test bot",
        "running_version": 0,
        "running_version_info": {
            "metadata": {"author_username": "no-auth", "message": "init", "timestamp": RECENT_TIMESTAMP},
            "version": 0,
        },
        "last_versions": [
            {
                "version": 0,
                "metadata": {"timestamp": RECENT_TIMESTAMP, "message": "init", "author_username": "no-auth"},
            }
        ],
        "last_events": [
            {"timestamp": RECENT_TIMESTAMP, "username": "no-auth", "event": "edited", "new_version": 0},
            {"timestamp": RECENT_TIMESTAMP, "username": "no-auth", "event": "started", "version": 0},
        ],
        "forms_with_responses": [],
        "last_errors": [],
        "admin_chat_ids": [],
        "alert_chat_id": None,
    }

    assert isinstance(constructor.runner, MockBotRunner)
    bot_runner = constructor.runner.running["no-auth"]["mybot"]
    assert isinstance(bot_runner.bot, MockedAsyncTeleBot)
    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)
    bot.method_calls.clear()
    # several users fill out the form
    for user_id, first_name in [(1, "AAA"), (2, "BBB"), (3, "CCC")]:
        # using start command to start the form
        await bot.process_new_updates([tg_update_message_to_bot(user_id, first_name=first_name, text="/start")])
        assert len(bot.method_calls) == 1
        assert_method_call_kwargs_include(
            bot.method_calls["send_message"],
            [
                {"chat_id": user_id, "text": "Hello welcome to the form testing bot\n\n/cancel — to cancel"},
                {"chat_id": user_id, "text": "Please answer the first question"},
            ],
        )
        bot.method_calls.clear()

        await bot.process_new_updates(
            [tg_update_message_to_bot(user_id, first_name=first_name, text=f"First answer by user #{user_id}")]
        )
        assert len(bot.method_calls) == 1
        assert_method_call_kwargs_include(
            bot.method_calls["send_message"],
            [{"chat_id": user_id, "text": "Please answer the second question"}],
        )
        bot.method_calls.clear()

        await bot.process_new_updates(
            [tg_update_message_to_bot(user_id, first_name=first_name, text=f"Second answer by user #{user_id}")]
        )
        assert len(bot.method_calls) == 1
        assert_method_call_kwargs_include(
            bot.method_calls["send_message"],
            [
                {
                    "chat_id": user_id,
                    "text": (
                        f"<b>one</b>: First answer by user #{user_id}\n"
                        + f"<b>two</b>: Second answer by user #{user_id}"
                    ),
                }
            ],
        )
        bot.method_calls.clear()

    # checking bot info, the form should be there
    resp = await client.get("/api/info/mybot")
    assert resp.status == 200
    assert mask_recent_timestamps(await resp.json()) == {
        "bot_id": "mybot",
        "display_name": "my test bot",
        "running_version": 0,
        "running_version_info": {
            "metadata": {"author_username": "no-auth", "message": "init", "timestamp": RECENT_TIMESTAMP},
            "version": 0,
        },
        "last_versions": [
            {
                "version": 0,
                "metadata": {
                    "timestamp": RECENT_TIMESTAMP,
                    "message": "init",
                    "author_username": "no-auth",
                },
            }
        ],
        "last_events": [
            {"timestamp": RECENT_TIMESTAMP, "username": "no-auth", "event": "edited", "new_version": 0},
            {"timestamp": RECENT_TIMESTAMP, "username": "no-auth", "event": "started", "version": 0},
        ],
        "forms_with_responses": [
            {
                "form_block_id": "form-block-123",
                "prompt": "Hello welcome to the form testing bot",
                "title": None,
                "total_responses": 3,
            }
        ],
        "last_errors": [],
        "admin_chat_ids": [],
        "alert_chat_id": None,
    }

    # finally, calling the form results api to get user's responses
    resp = await client.get("/api/forms/mybot/form-block-123/responses")
    assert resp.status == 200
    assert mask_recent_timestamps(await resp.json()) == {
        "info": {
            "form_block_id": "form-block-123",
            "prompt": "Hello welcome to the form testing bot",
            "title": None,
            "field_names": {"form-field-1": "one", "form-field-2": "two"},
            "total_responses": 3,
        },
        "results": [
            {
                "timestamp": RECENT_TIMESTAMP,
                "user": "AAA",
                "form-field-1": "First answer by user #1",
                "form-field-2": "Second answer by user #1",
            },
            {
                "timestamp": RECENT_TIMESTAMP,
                "user": "BBB",
                "form-field-1": "First answer by user #2",
                "form-field-2": "Second answer by user #2",
            },
            {
                "timestamp": RECENT_TIMESTAMP,
                "user": "CCC",
                "form-field-1": "First answer by user #3",
                "form-field-2": "Second answer by user #3",
            },
        ],
        "bot_info": {
            "bot_id": "mybot",
            "display_name": "my test bot",
            "forms_with_responses": [],
            "last_errors": [],
            "last_events": [
                {"event": "started", "timestamp": "<recent timestamp>", "username": "no-auth", "version": 0}
            ],
            "last_versions": [
                {
                    "metadata": {"author_username": "no-auth", "message": "init", "timestamp": "<recent " "timestamp>"},
                    "version": 0,
                }
            ],
            "running_version": 0,
            "running_version_info": {
                "metadata": {"author_username": "no-auth", "message": "init", "timestamp": RECENT_TIMESTAMP},
                "version": 0,
            },
            "admin_chat_ids": [],
            "alert_chat_id": None,
        },
    }

    # update form title to something custom
    resp = await client.put("/api/forms/mybot/form-block-123/title", data="updated form name")
    assert resp.status == 200

    # retrieve the results again but with pagination
    resp = await client.get("/api/forms/mybot/form-block-123/responses?offset=1&count=1")
    assert resp.status == 200
    assert mask_recent_timestamps(await resp.json()) == {
        "info": {
            "form_block_id": "form-block-123",
            "prompt": "Hello welcome to the form testing bot",
            "title": "updated form name",
            "field_names": {"form-field-1": "one", "form-field-2": "two"},
            "total_responses": 3,
        },
        "results": [
            {
                "timestamp": RECENT_TIMESTAMP,
                "user": "BBB",
                "form-field-1": "First answer by user #2",
                "form-field-2": "Second answer by user #2",
            },
        ],
        "bot_info": {
            "bot_id": "mybot",
            "display_name": "my test bot",
            "forms_with_responses": [],
            "last_errors": [],
            "last_events": [
                {"event": "started", "timestamp": "<recent timestamp>", "username": "no-auth", "version": 0}
            ],
            "last_versions": [
                {
                    "metadata": {"author_username": "no-auth", "message": "init", "timestamp": "<recent " "timestamp>"},
                    "version": 0,
                }
            ],
            "running_version": 0,
            "running_version_info": {
                "metadata": {"author_username": "no-auth", "message": "init", "timestamp": RECENT_TIMESTAMP},
                "version": 0,
            },
            "admin_chat_ids": [],
            "alert_chat_id": None,
        },
    }

    # also, exporting results to CSV
    responses = await (await client.get("/api/forms/mybot/form-block-123/responses")).json()
    timestamps = [datetime.datetime.fromtimestamp(r["timestamp"]).isoformat() for r in responses["results"]]
    assert len(timestamps) == 3

    resp = await client.get("/api/forms/mybot/form-block-123/export")
    assert resp.status == 200
    csv_text = await resp.text()
    assert (
        csv_text.strip().replace("\r\n", "\n")
        == f"""
Timestamp,User,one,two
{timestamps[0]},AAA,First answer by user #1,Second answer by user #1
{timestamps[1]},BBB,First answer by user #2,Second answer by user #2
{timestamps[2]},CCC,First answer by user #3,Second answer by user #3
""".strip()
    )
