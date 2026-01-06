import time
from typing import Any, Tuple

import aiohttp.web
from pytest_aiohttp.plugin import AiohttpClient  # type: ignore
from telebot.metrics import TelegramUpdateMetrics
from telebot.test_util import MockedAsyncTeleBot

from telebot_constructor.app import ModuliApp
from tests.test_app.conftest import MockBotRunner
from tests.utils import (
    RECENT_TIMESTAMP,
    mask_recent_timestamps,
    tg_update_message_to_bot,
)


async def test_bot_level_errors(
    constructor_app: Tuple[ModuliApp, aiohttp.web.Application],
    aiohttp_client: AiohttpClient,
) -> None:
    constructor, web_app = constructor_app
    client = await aiohttp_client(web_app)

    # saving a token
    resp = await client.post("/api/secrets/test-token", data="hello")
    assert resp.status == 200

    # saving a bot config
    resp = await client.post(
        "/api/config/mybot",
        params={"new": "true"},
        json={
            "config": {
                "token_secret_name": "test-token",
                "user_flow_config": {
                    "entrypoints": [
                        {
                            "command": {
                                "entrypoint_id": "start",
                                "command": "start",
                                "next_block_id": "error-block",
                            },
                        }
                    ],
                    "blocks": [{"error": {"block_id": "error-block"}}],
                    "node_display_coords": {},
                },
            },
            "display_name": "my test bot",
            "start": True,
            "version_message": "init",
        },
    )
    assert resp.status == 201

    # users are interacting with bot and triggering errors
    assert isinstance(constructor.runner, MockBotRunner)
    bot_runner = constructor.runner.running["no-auth"]["mybot"]
    assert isinstance(bot_runner.bot, MockedAsyncTeleBot)
    bot = bot_runner.bot
    assert isinstance(bot, MockedAsyncTeleBot)
    bot.method_calls.clear()
    await bot.process_new_updates(
        [
            tg_update_message_to_bot(
                user_id=123,
                first_name="john pork",
                text="/start",
                metrics=TelegramUpdateMetrics(bot_prefix="test-bot", received_at=time.time()),
            )
        ]
    )
    assert not bot.method_calls

    def check_error(error: Any, user_id: int) -> None:
        assert isinstance(error, dict)
        assert error["timestamp"] == RECENT_TIMESTAMP
        assert error["message"].startswith(
            "Error processing update with handler 'telebot_constructor.user_flow.entrypoints.command."
            + "CommandEntryPoint.setup.<locals>.cmd_handler': Message({'content_type': 'text', 'id': 1, "
            + "'message_id': 1, 'from_user': {'id': "
            + f"{user_id}, 'is_bot': False, 'first_name': 'john pork'"
        )
        assert error["exc_type"] == "RuntimeError"
        assert error["exc_data"] == "RuntimeError: User entered the error block (self.block_id='error-block')"
        assert error["exc_traceback"].endswith(
            'raise RuntimeError(f"User entered the error block ({self.block_id=!r})")'
        )

    resp = await client.get("/api/info/mybot")
    assert resp.status == 200
    errors = mask_recent_timestamps(await resp.json())["last_errors"]  # type: ignore
    assert len(errors) == 1
    check_error(errors[0], user_id=123)

    await bot.process_new_updates(
        [
            tg_update_message_to_bot(
                user_id=user_id,
                first_name="john pork",
                text="/start",
                metrics=TelegramUpdateMetrics(bot_prefix="test-bot", received_at=time.time()),
            )
            for user_id in range(5)
        ]
    )

    # calling the bot errors api to get the full list (3 last errors in this case)
    resp = await client.get("/api/errors/mybot?count=3")
    assert resp.status == 200
    errors = mask_recent_timestamps(await resp.json())["errors"]  # type: ignore
    for user_id, error in zip((2, 3, 4), errors):
        check_error(error, user_id=user_id)
