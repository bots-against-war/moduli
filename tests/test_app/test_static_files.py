import re
from typing import Tuple

import aiohttp.web
from pytest_aiohttp.plugin import AiohttpClient  # type: ignore

from telebot_constructor.app import ModuliApp


async def test_serve_index(
    constructor_app: Tuple[ModuliApp, aiohttp.web.Application], aiohttp_client: AiohttpClient
) -> None:
    constructor, web_app = constructor_app
    client = await aiohttp_client(web_app)

    resp = await client.get("/")
    assert resp.status == 404
    assert re.match(r"^404: Static path /.*/landing\.html does not exist$", await resp.text("utf-8"))

    (constructor.static_files_dir / "landing.html").write_text("landing page")
    (constructor.static_files_dir / "index.html").write_text("constructor app")

    resp = await client.get("/")
    assert resp.status == 200
    assert await resp.text("utf-8") == "landing page"
    assert resp.content_type == "text/html"

    resp = await client.get("/whatever/weird/path/we/use/in/client/side/routing")
    assert resp.status == 200
    assert await resp.text("utf-8") == "constructor app"
    assert resp.content_type == "text/html"


async def test_serve_static_files(
    constructor_app: Tuple[ModuliApp, aiohttp.web.Application], aiohttp_client: AiohttpClient
) -> None:
    constructor, web_app = constructor_app
    client = await aiohttp_client(web_app)

    assets_dir = constructor.static_files_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "some-asset.js").write_text("console.log(foo);")

    resp = await client.get("/assets/some-asset.js")
    assert resp.status == 200
    assert await resp.text("utf-8") == "console.log(foo);"


async def test_cors(
    constructor_app: Tuple[ModuliApp, aiohttp.web.Application], aiohttp_client: AiohttpClient
) -> None:
    _, web_app = constructor_app
    client = await aiohttp_client(web_app)

    resp = await client.options("/whatever", headers={"Origin": "http://example.com"})

    assert resp.status == 200
    headers = dict(resp.headers)
    headers.pop("Date")
    headers.pop("Server")
    assert headers == {
        "Access-Control-Allow-Origin": "http://localhost:8081",
        "Access-Control-Allow-Headers": "Content-Type, X-Telebot-Constructor-Filename",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        "Access-Control-Max-Age": "300",
        "Content-Length": "0",
        "Content-Type": "text/plain; charset=utf-8",
        # "Date": "Mon, 23 Oct 2023 17:59:37 GMT",
        # "Server": "Python/3.10 aiohttp/3.8.6",
    }


async def test_prefilled_messages(
    constructor_app: Tuple[ModuliApp, aiohttp.web.Application],
    aiohttp_client: AiohttpClient,
) -> None:
    _, web_app = constructor_app
    client = await aiohttp_client(web_app)

    for _ in range(3):
        resp = await client.get("/api/prefilled-messages")
        assert resp.status == 200
        resp_json = await resp.json()
        assert isinstance(resp_json, dict)
        assert list(resp_json.keys()) == [
            "cancel_command_is",
            "field_is_skippable",
            "field_is_not_skippable",
            "unsupported_command",
            "please_enter_correct_value",
            "empty_text_error_msg",
            "not_an_integer_error_msg",
            "not_an_integer_list_error_msg",
            "bad_time_format_msg",
            "invalid_enum_error_msg",
            "attachments_expected_error_msg",
            "only_one_media_message_allowed_error_msg",
            "bad_attachment_type_error_msg",
            "please_use_inline_menu",
            "anti_spam_warning",
        ]

        assert all(["/skip" in msg for msg in resp_json["field_is_skippable"].values()])
        assert all("/cancel" in msg for msg in resp_json["cancel_command_is"].values())
