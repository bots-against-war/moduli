"""Example of running Telebot Constructor as part of a larger app"""

import asyncio
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import web
from redis.asyncio import Redis
from telebot import AsyncTeleBot
from telebot.webhook import WebhookApp
from telebot_components.redis_utils.emulation import PersistentRedisEmulation
from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.utils.secrets import RedisSecretStore

from telebot_constructor.app import ModuliApp
from telebot_constructor.auth.auth import Auth, GroupChatAuth, NoAuth
from telebot_constructor.auth.telegram_auth import TelegramAuth
from telebot_constructor.telegram_files_downloader import (
    RedisCacheTelegramFilesDownloader,
)


async def main() -> None:
    app = WebhookApp(base_url="https://localhost:8888")
    routes = web.RouteTableDef()

    @routes.get("/")
    async def host_app_index(request: web.Request) -> web.Response:
        return web.Response(text="host app index")

    app.aiohttp_app.add_routes(routes)

    if bool(os.environ.get("TELEBOT_CONSTRUCTOR_USE_REDIS_EMULATION")):
        logging.info("Using redis emulation")
        redis: RedisInterface = PersistentRedisEmulation()  # type: ignore
    else:
        logging.info("Using real redis")
        redis_url = urlparse(os.environ["REDIS_URL"])
        redis = Redis(  # type: ignore
            host=redis_url.hostname or "",
            port=redis_url.port or 0,
            username=redis_url.username,
            password=redis_url.password,
        )

    secret_store = RedisSecretStore(
        redis=redis,
        encryption_key=os.environ["SECRETS_ENCRYPTION_KEY"],
        secret_max_len=10 * 1024,
        secrets_per_user=10,
        scope_secrets_to_user=False,
    )

    telegram_files_downloader = RedisCacheTelegramFilesDownloader(redis=redis)

    auth: Auth
    auth_type = os.environ.get("AUTH", "NOOP").upper()
    if auth_type == "TELEGRAM":
        logging.info("Using Telegram-based auth")
        auth = TelegramAuth(
            redis=redis,
            bot=AsyncTeleBot(token=os.environ["TELEGRAM_AUTH_BOT_TOKEN"]),
            telegram_files_downloader=telegram_files_downloader,
        )
    elif auth_type == "GROUP_CHAT":
        logging.info("Using Telegram group auth")
        auth = GroupChatAuth(
            redis=redis,
            bot=AsyncTeleBot(token=os.environ["GROUP_CHAT_AUTH_BOT_TOKEN"]),
            auth_chat_id=int(os.environ["GROUP_CHAT_AUTH_CHAT_ID"]),
            telegram_files_downloader=telegram_files_downloader,
        )
    elif auth_type == "NOOP":
        logging.info("Using noop auth")
        auth = NoAuth(owner_chat_id=int(os.environ["OWNER_CHAT_ID"]))
    else:
        raise ValueError(f"Unexpected auth type: {auth_type!r}")

    tbc_app = ModuliApp(
        redis=redis,
        auth=auth,
        secret_store=secret_store,
        static_files_dir=Path("frontend/dist"),
        telegram_files_downloader=telegram_files_downloader,
    )

    await tbc_app.setup_on_webhook_app(app)

    await app.run(port=8088)


asyncio.run(main())
