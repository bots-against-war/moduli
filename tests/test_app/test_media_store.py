import aiohttp.web
from pytest_aiohttp.plugin import AiohttpClient  # type: ignore

from telebot_constructor.app import ModuliApp


async def test_media_api(
    constructor_app: tuple[ModuliApp, aiohttp.web.Application],
    aiohttp_client: AiohttpClient,
) -> None:
    _, web_app = constructor_app
    client = await aiohttp_client(web_app)

    content = b"abcde"
    resp = await client.post("/api/media", data=content, headers={"X-Telebot-Constructor-Filename": "image.png"})
    assert resp.status == 200
    media_id = await resp.text()

    resp = await client.get(f"/api/media/{media_id}")
    assert resp.status == 200
    assert resp.headers["Content-Type"] == "image/png"
    assert resp.headers["X-Telebot-Constructor-Filename"] == "image.png"
    assert await resp.read() == content

    resp = await client.delete(f"/api/media/{media_id}")
    assert resp.status == 200

    resp = await client.get(f"/api/media/{media_id}")
    assert resp.status == 404
    resp = await client.delete(f"/api/media/{media_id}")
    assert resp.status == 404
