import collections
import tempfile
from pathlib import Path
from typing import AsyncGenerator

import aiohttp.web
import pytest
from cryptography.fernet import Fernet
from telebot import AsyncTeleBot
from telebot.runner import BotRunner
from telebot.test_util import MockedAsyncTeleBot
from telebot_components.redis_utils.emulation import RedisEmulation
from telebot_components.utils.secrets import RedisSecretStore

from telebot_constructor.app import TelebotConstructorApp
from telebot_constructor.auth.auth import NoAuth
from telebot_constructor.runners import ConstructedBotRunner


class MockBotRunner(ConstructedBotRunner):
    def __init__(self) -> None:
        self.running: dict[str, dict[str, BotRunner]] = collections.defaultdict(dict)

    async def start(self, username: str, bot_name: str, bot_runner: BotRunner) -> bool:
        self.running[username][bot_name] = bot_runner
        return True

    async def stop(self, username: str, bot_name: str) -> bool:
        stopped = self.running[username].pop(bot_name, None)
        return stopped is not None

    async def cleanup(self) -> None:
        pass


_MOCKED_ASYNC_TELEBOT_CACHE: dict[str, AsyncTeleBot] = dict()


def mocked_async_telebot_factory(token: str) -> AsyncTeleBot:
    cached = _MOCKED_ASYNC_TELEBOT_CACHE.get(token)
    if cached is not None:
        return cached
    bot = MockedAsyncTeleBot(token)
    _MOCKED_ASYNC_TELEBOT_CACHE[token] = bot
    return bot


@pytest.fixture
async def constructor_app() -> AsyncGenerator[tuple[TelebotConstructorApp, aiohttp.web.Application], None]:
    redis = RedisEmulation()
    with tempfile.TemporaryDirectory() as tempdir:
        telebot_constructor_app = TelebotConstructorApp(
            redis=redis,
            auth=NoAuth(),
            secret_store=RedisSecretStore(
                redis,
                encryption_key=Fernet.generate_key().decode("utf-8"),
                secrets_per_user=10,
                secret_max_len=1024,
                scope_secrets_to_user=True,
            ),
            static_files_dir=Path(tempdir),
        )
        telebot_constructor_app._runner = MockBotRunner()
        telebot_constructor_app._bot_factory = mocked_async_telebot_factory
        await telebot_constructor_app.setup()
        aiohttp_app = await telebot_constructor_app.create_constructor_web_app()
        try:
            yield (telebot_constructor_app, aiohttp_app)
        finally:
            await telebot_constructor_app.cleanup()
