import pytest
from aioresponses import aioresponses
from telebot.test_util import MockedAsyncTeleBot
from telebot_components.redis_utils.emulation import RedisEmulation

from telebot_constructor.bot_config import BotConfig, UserFlowConfig
from telebot_constructor.construct import construct_bot
from tests.utils import dummy_errors_store, dummy_form_results_store, dummy_secret_store

EMPTY_USER_FLOW_CONFIG = UserFlowConfig(
    entrypoints=[],
    blocks=[],
    node_display_coords={},
)


async def test_construct_empty_bot() -> None:
    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)
    username = "test-user"
    await secret_store.save_secret(secret_name="empty-bot-token", secret_value="mock-token", owner_id=username)
    await construct_bot(
        owner_id=username,
        bot_id="empty-bot-test",
        bot_config=BotConfig(
            token_secret_name="empty-bot-token", display_name="Test bot", user_flow_config=EMPTY_USER_FLOW_CONFIG
        ),
        form_results_store=dummy_form_results_store(),
        errors_store=dummy_errors_store(),
        secret_store=secret_store,
        owner_chat_id=0,
        redis=redis,
        _bot_factory=MockedAsyncTeleBot,
    )


async def test_missing_token_secret() -> None:
    redis = RedisEmulation()
    with pytest.raises(ValueError):
        await construct_bot(
            owner_id="some-user",
            bot_id="bot-test",
            bot_config=BotConfig(
                token_secret_name="empty-bot-token", display_name="Test bot", user_flow_config=EMPTY_USER_FLOW_CONFIG
            ),
            form_results_store=dummy_form_results_store(),
            errors_store=dummy_errors_store(),
            secret_store=dummy_secret_store(redis),
            owner_chat_id=0,
            redis=redis,
            _bot_factory=MockedAsyncTeleBot,
        )


async def test_bot_token_validation_failed() -> None:
    redis = RedisEmulation()
    secret_store = dummy_secret_store(redis)
    username = "test-user"
    await secret_store.save_secret(secret_name="token", secret_value="123456789", owner_id=username)
    with aioresponses() as mock_http:
        mock_http.get("https://api.telegram.org/bot123456789/getMe", status=404, repeat=True)
        with pytest.raises(ValueError, match="Failed to get bot user with getMe, the token is probably invalid"):
            await construct_bot(
                owner_id=username,
                bot_id="test",
                bot_config=BotConfig(
                    token_secret_name="token",
                    display_name="Test bot",
                    user_flow_config=EMPTY_USER_FLOW_CONFIG,
                ),
                form_results_store=dummy_form_results_store(),
                errors_store=dummy_errors_store(),
                owner_chat_id=0,
                secret_store=secret_store,
                redis=redis,
            )
