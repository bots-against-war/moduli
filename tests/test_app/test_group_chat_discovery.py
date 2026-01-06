from typing import Tuple

import aiohttp.web
from pytest_aiohttp.plugin import AiohttpClient  # type: ignore
from telebot import types as tg
from telebot.test_util import MockedAsyncTeleBot

from telebot_constructor.app import ModuliApp
from tests.test_app.conftest import MockBotRunner
from tests.utils import tg_update_message_to_bot


async def test_group_chat_discovery(
    constructor_app: Tuple[ModuliApp, aiohttp.web.Application],
    aiohttp_client: AiohttpClient,
) -> None:
    constructor, web_app = constructor_app
    client = await aiohttp_client(web_app)

    resp = await client.post("/api/secrets/my-test-bot-token", data="my-token")
    assert resp.status == 200

    resp = await client.post(
        "/api/config/my-test-bot",
        params={"new": "true"},
        json={
            "config": {
                "display_name": "my bot",
                "token_secret_name": "my-test-bot-token",
                "user_flow_config": {
                    "entrypoints": [],
                    "blocks": [],
                    "node_display_coords": {},
                },
            },
            "start": False,
            "version_message": None,
        },
    )
    print(await resp.json())
    assert resp.status == 201

    resp = await client.post("/api/start-group-chat-discovery/my-test-bot")
    assert resp.status == 200

    assert isinstance(constructor.runner, MockBotRunner)
    bot_runner = constructor.runner.running["no-auth"]["my-test-bot"]
    assert isinstance(bot_runner.bot, MockedAsyncTeleBot)
    await bot_runner.bot.process_new_updates(
        [
            tg_update_message_to_bot(
                user_id=123,
                first_name="User",
                text="/discover_chat",
                group_chat_id=456,
            )
        ]
    )

    resp = await client.post("/api/stop-group-chat-discovery/my-test-bot")
    assert resp.status == 200

    bot_runner.bot.add_return_values("get_chat", tg.Chat(id=456, type="supergroup", title="some group chat"))
    resp = await client.get("/api/available-group-chats/my-test-bot")
    assert resp.status == 200
    assert await resp.json() == [
        {
            "id": 456,
            "type": "supergroup",
            "title": "some group chat",
            "description": None,
            "username": None,
            "is_forum": None,
            "photo": None,
        }
    ]
