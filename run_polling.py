import asyncio
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from redis.asyncio import Redis
from telebot import AsyncTeleBot
from telebot_components.redis_utils.emulation import PersistentRedisEmulation
from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.utils.alerts import configure_alerts
from telebot_components.utils.secrets import RedisSecretStore

from telebot_constructor.app import TelebotConstructorApp
from telebot_constructor.auth.auth import Auth, GroupChatAuth, NoAuth
from telebot_constructor.auth.telegram_auth import TelegramAuth
from telebot_constructor.store.media import (
    AwsS3Credentials,
    AwsS3MediaStore,
    FilesystemMediaStore,
    MediaStore,
)
from telebot_constructor.telegram_files_downloader import (
    RedisCacheTelegramFilesDownloader,
)

logging.basicConfig(level=logging.INFO if os.environ.get("IS_HEROKU") else logging.DEBUG)


async def main() -> None:
    try:
        configure_alerts(token=os.environ["ALERTS_BOT_TOKEN"], alerts_channel_id=int(os.environ["ALERTS_CHANNEL_ID"]))
    except Exception:
        logging.info("Failed to configure alerts, running without them", exc_info=True)

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
            ssl=True,
            ssl_cert_reqs=None,  # type: ignore
        )
        start_time = time.time()
        await redis.ping()  # type: ignore
        ping_time = start_time - time.time()
        logging.info(f"Redis pinged in {ping_time:.3f} sec")

    secret_store = RedisSecretStore(
        redis=redis,
        encryption_key=os.environ["SECRETS_ENCRYPTION_KEY"],
        secret_max_len=10 * 1024,
        secrets_per_user=100,
        scope_secrets_to_user=True,
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
        auth = NoAuth()
    else:
        raise ValueError(f"Unexpected auth type: {auth_type!r}")

    try:
        media_store: MediaStore = AwsS3MediaStore(
            credentials=AwsS3Credentials.model_validate_json(os.environ["MEDIA_STORE_AWS_S3_CREDENTIALS"])
        )
        logging.info("AWS S3 media store set up")
    except Exception:
        media_dir = Path(".media").absolute()
        media_dir.mkdir(exist_ok=True)
        media_store = FilesystemMediaStore(media_dir)
        logging.info("Filesystem media store set up")

    app = TelebotConstructorApp(
        redis=redis,
        auth=auth,
        secret_store=secret_store,
        static_files_dir=Path("frontend/dist"),
        telegram_files_downloader=telegram_files_downloader,
        media_store=media_store,
    )
    logging.info("Running app with polling")
    await app.run_polling(port=int(os.environ.get("PORT", 8088)))


if __name__ == "__main__":
    asyncio.run(main())
