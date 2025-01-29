from typing import Tuple

import aiohttp.web
from pytest_aiohttp.plugin import AiohttpClient  # type: ignore

from telebot_constructor.app import ModuliApp


async def test_basic_secret_crud(
    constructor_app: Tuple[ModuliApp, aiohttp.web.Application],
    aiohttp_client: AiohttpClient,
) -> None:
    _, web_app = constructor_app
    client = await aiohttp_client(web_app)

    resp = await client.post("/api/secrets/my-secret", data="i like snow")
    assert resp.status == 200

    resp = await client.get("/api/secrets")
    assert resp.status == 200
    assert await resp.json() == ["my-secret"]

    resp = await client.delete("/api/secrets/my-secret")
    assert resp.status == 200

    resp = await client.get("/api/secrets")
    assert resp.status == 200
    assert await resp.json() == []


async def test_token_secret_is_unique(
    constructor_app: Tuple[ModuliApp, aiohttp.web.Application],
    aiohttp_client: AiohttpClient,
) -> None:
    constructor, web_app = constructor_app
    client = await aiohttp_client(web_app)

    resp = await client.post("/api/secrets/my-token?is_token=true", data="token")
    assert resp.status == 200

    resp = await client.post("/api/secrets/my-token?is_token=true", data="token")
    assert resp.status == 400

    resp = await client.delete("/api/secrets/my-token?is_token=true")
    assert resp.status == 200

    resp = await client.post("/api/secrets/my-token?is_token=true", data="token")
    assert resp.status == 200
