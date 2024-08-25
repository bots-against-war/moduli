import aiohttp.web
from pytest_aiohttp.plugin import AiohttpClient  # type: ignore

from telebot_constructor.app import TelebotConstructorApp
from tests.utils import RECENT_TIMESTAMP, mask_recent_timestamps


async def test_get_logged_in_user(
    constructor_app: tuple[TelebotConstructorApp, aiohttp.web.Application],
    aiohttp_client: AiohttpClient,
) -> None:
    _, web_app = constructor_app
    client = await aiohttp_client(web_app)

    resp = await client.get("/api/logged-in-user")
    assert resp.status == 200
    assert await resp.json() == {
        "auth_type": "no_auth",
        "username": "no-auth",
        "name": "Anonymous user",
        "display_username": None,
        "userpic": None,
    }


async def test_bot_config(
    constructor_app: tuple[TelebotConstructorApp, aiohttp.web.Application],
    aiohttp_client: AiohttpClient,
) -> None:
    _, web_app = constructor_app
    client = await aiohttp_client(web_app)

    # saving secret
    bot_name = "test-bot-1312"
    resp = await client.post("/api/secrets/test-1312-token", data="token")
    assert resp.status == 200

    # saving first version of bot config
    bot_config_1 = {
        "token_secret_name": "test-1312-token",
        "user_flow_config": {"entrypoints": [], "blocks": [], "node_display_coords": {}},
        "display_name": None,
    }
    resp = await client.post(
        f"/api/config/{bot_name}",
        json={
            "config": bot_config_1,
            "start": False,
            "version_message": "init message",
            "display_name": "my bot",
        },
    )
    assert resp.status == 201

    # checking that we can read it back
    resp = await client.get(f"/api/config/{bot_name}")
    assert resp.status == 200
    assert await resp.json() == bot_config_1

    # checking basic bot info
    resp = await client.get("/api/info")
    assert resp.status == 200
    resp_json_1 = mask_recent_timestamps(await resp.json())
    assert resp_json_1 == {
        "test-bot-1312": {
            "bot_name": "test-bot-1312",
            "display_name": "my bot",
            "running_version": None,
            "last_versions": [{"version": 0, "metadata": {"timestamp": RECENT_TIMESTAMP, "message": "init message"}}],
            "last_events": [
                {"timestamp": RECENT_TIMESTAMP, "username": "no-auth", "event": "edited", "new_version": 0}
            ],
            "forms_with_responses": [],
            "last_errors": [],
        }
    }
    bot_created_event = resp_json_1[bot_name]["last_events"][0]  # type: ignore

    # starting bot
    resp = await client.post(f"/api/start/{bot_name}", json={"version": 0})
    assert resp.status == 201

    # checking info again, corresponding "started" event should be there
    resp = await client.get("/api/info")
    assert resp.status == 200
    resp_json_2 = mask_recent_timestamps(await resp.json())
    assert resp_json_2 == {
        "test-bot-1312": {
            "bot_name": "test-bot-1312",
            "display_name": "my bot",
            "running_version": 0,
            "last_versions": [{"version": 0, "metadata": {"timestamp": RECENT_TIMESTAMP, "message": "init message"}}],
            "last_events": [
                bot_created_event,
                {"timestamp": RECENT_TIMESTAMP, "username": "no-auth", "event": "started", "version": 0},
            ],
            "forms_with_responses": [],
            "last_errors": [],
        }
    }
    bot_started_event = resp_json_2[bot_name]["last_events"][1]  # type: ignore

    # checking same info but with a bot-specific endpoint
    resp = await client.get(f"/api/info/{bot_name}")
    assert resp.status == 200
    assert mask_recent_timestamps(await resp.json()) == resp_json_2[bot_name]  # type: ignore

    # update display name and check it's changed in the info
    resp = await client.put(f"/api/display-name/{bot_name}", json={"display_name": "changed display name"})
    assert resp.status == 200
    resp = await client.get(f"/api/info/{bot_name}")
    assert resp.status == 200
    assert (await resp.json())["display_name"] == "changed display name"

    # updating bot config
    bot_config_2 = {
        "token_secret_name": "test-1312-token",
        "user_flow_config": {
            "entrypoints": [
                {
                    "command": {
                        "entrypoint_id": "123",
                        "command": "start",
                        "next_block_id": None,
                        "scope": "private",
                        "short_description": None,
                    },
                    "catch_all": None,
                    "regex": None,
                },
            ],
            "blocks": [],
            "node_display_coords": {},
        },
        "display_name": None,
    }
    resp = await client.post(
        f"/api/config/{bot_name}",
        json={
            "config": bot_config_2,
            "start": True,
            "version_message": "bot config update",
        },
    )
    assert resp.status == 200

    # checking that it's saved indeed and we can retrieve the last version in multiple ways
    for url in [f"/api/config/{bot_name}", f"/api/config/{bot_name}?version=-1", f"/api/config/{bot_name}?version=1"]:
        resp = await client.get(url)
        assert resp.status == 200
        assert await resp.json() == bot_config_2

    # ... but we can always retrieve the old version too!
    resp = await client.get(f"/api/config/{bot_name}?version=0")
    assert resp.status == 200
    assert await resp.json() == bot_config_1

    # and this update must be reflected in bot info
    resp = await client.get(f"/api/info/{bot_name}")
    assert resp.status == 200
    resp_json_3 = mask_recent_timestamps(await resp.json())
    assert resp_json_3 == {
        "bot_name": "test-bot-1312",
        "display_name": "changed display name",
        "running_version": 1,
        "last_versions": [
            {"version": 0, "metadata": {"timestamp": RECENT_TIMESTAMP, "message": "init message"}},
            {"version": 1, "metadata": {"timestamp": RECENT_TIMESTAMP, "message": "bot config update"}},
        ],
        "last_events": [
            bot_created_event,
            bot_started_event,
            {"timestamp": RECENT_TIMESTAMP, "username": "no-auth", "event": "edited", "new_version": 1},
            {"timestamp": RECENT_TIMESTAMP, "username": "no-auth", "event": "stopped"},
            {"timestamp": RECENT_TIMESTAMP, "username": "no-auth", "event": "started", "version": 1},
        ],
        "forms_with_responses": [],
        "last_errors": [],
    }
    bot_edited_event, bot_stopped_event, bot_started_again_event = resp_json_3["last_events"][2:]  # type: ignore

    # now let's stop the bot
    resp = await client.post(f"/api/stop/{bot_name}")
    assert resp.status == 200

    # check it's reflected in the info
    resp = await client.get(f"/api/info/{bot_name}")
    assert resp.status == 200
    resp_json_4 = mask_recent_timestamps(await resp.json())
    assert resp_json_4 == {
        "bot_name": "test-bot-1312",
        "display_name": "changed display name",
        "running_version": None,
        "last_versions": [
            {"version": 0, "metadata": {"timestamp": RECENT_TIMESTAMP, "message": "init message"}},
            {"version": 1, "metadata": {"timestamp": RECENT_TIMESTAMP, "message": "bot config update"}},
        ],
        "last_events": [
            bot_created_event,
            bot_started_event,
            bot_edited_event,
            bot_stopped_event,
            bot_started_again_event,
            {"timestamp": RECENT_TIMESTAMP, "username": "no-auth", "event": "stopped"},
        ],
        "forms_with_responses": [],
        "last_errors": [],
    }

    # let's delete this bot for good
    resp = await client.delete(f"/api/config/{bot_name}")
    assert resp.status == 200
    assert await resp.json() == bot_config_2

    # try to see it one more time and fail
    resp = await client.get(f"/api/info/{bot_name}")
    assert resp.status == 404
    assert await resp.text() == "404: Bot id not found"
