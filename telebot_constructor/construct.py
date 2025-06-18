import itertools
import logging
from typing import Callable, Coroutine, Optional, Type

from telebot import AsyncTeleBot
from telebot import types as tg
from telebot.metrics import TelegramUpdateMetricsHandler
from telebot.runner import AuxBotEndpoint, BotRunner
from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.stores.banned_users import BannedUsersStore
from telebot_components.utils.secrets import SecretStore

from telebot_constructor.bot_config import BotConfig
from telebot_constructor.constants import CONSTRUCTOR_PREFIX
from telebot_constructor.group_chat_discovery import GroupChatDiscoveryHandler
from telebot_constructor.store.errors import BotSpecificErrorsStore
from telebot_constructor.store.form_results import BotSpecificFormResultsStore
from telebot_constructor.store.media import UserSpecificMediaStore
from telebot_constructor.user_flow.types import BotCommandInfo
from telebot_constructor.utils import log_prefix
from telebot_constructor.utils.rate_limit_retry import rate_limit_retry

BotFactory = (
    Type[AsyncTeleBot] | Callable[..., AsyncTeleBot]
)  # callable must have the same args as AsyncTeleBot constructor but I can't find the proper typing


async def make_bare_bot(
    owner_id: str,
    bot_id: str,
    bot_config: BotConfig,
    secret_store: SecretStore,
    update_metrics_handler: Optional[TelegramUpdateMetricsHandler] = None,
    _bot_factory: BotFactory = AsyncTeleBot,
) -> AsyncTeleBot:
    token = await secret_store.get_secret(secret_name=bot_config.token_secret_name, owner_id=owner_id)
    if token is None:
        raise ValueError(f"Token name {bot_config.token_secret_name!r} does not correspond to a valid secret")
    return _bot_factory(
        token,
        update_metrics_handler=update_metrics_handler,
        log_marker=log_prefix(owner_id, bot_id).strip("[]"),
    )


async def construct_bot(
    *,
    owner_id: str,
    bot_id: str,
    bot_config: BotConfig,
    secret_store: SecretStore,
    form_results_store: BotSpecificFormResultsStore,
    errors_store: BotSpecificErrorsStore,
    redis: RedisInterface,
    owner_chat_id: int,
    media_store: UserSpecificMediaStore | None = None,
    group_chat_discovery_handler: GroupChatDiscoveryHandler | None = None,
    _bot_factory: BotFactory = AsyncTeleBot,  # used for testing
) -> BotRunner:
    """Core bot construction function responsible for turning a config into a functional bot"""
    bot_prefix = f"{CONSTRUCTOR_PREFIX}/{owner_id}/{bot_id}"
    logger = logging.getLogger(__name__ + log_prefix(owner_id, bot_id))
    errors_store.instrument(logger)
    logger.info("Constructing bot")

    bot = await make_bare_bot(
        owner_id=owner_id,
        bot_id=bot_id,
        bot_config=bot_config,
        secret_store=secret_store,
        _bot_factory=_bot_factory,
    )
    # FIXME: now it's a global logger!!!
    errors_store.instrument(bot.logger)

    background_jobs: list[Coroutine[None, None, None]] = []
    aux_endpoints: list[AuxBotEndpoint] = []
    bot_commands: list[BotCommandInfo] = []

    try:
        bot_user: tg.User | None = None
        async for attempt in rate_limit_retry():
            with attempt:
                bot_user = await bot.get_me()
        assert bot_user is not None
        logger.info(f"Bot user loaded: {bot_user.to_json()}")
    except Exception:
        logger.exception("Error getting bot user, probably an invalid token")
        raise ValueError("Failed to get bot user with getMe, the token is probably invalid")

    banned_users_store = BannedUsersStore(redis=redis, bot_prefix=bot_prefix, cached=True)

    if bot_config.user_flow_config is not None:
        logger.info("Parsing user flow config")
        user_flow = bot_config.user_flow_config.to_user_flow()

        logger.info("Setting up user flow")
        user_flow_setup_result = await user_flow.setup(
            bot_prefix=bot_prefix,
            bot=bot,
            redis=redis,
            banned_users_store=banned_users_store,
            form_results_store=form_results_store,
            errors_store=errors_store,
            media_store=media_store,
            owner_chat_id=owner_chat_id,
        )

        logger.debug(f"Got result: {user_flow_setup_result}")
        background_jobs.extend(user_flow_setup_result.background_jobs)
        aux_endpoints.extend(user_flow_setup_result.aux_endpoints)
        bot_commands.extend(user_flow_setup_result.bot_commands)

    # TODO: cleanup for possible stale bot commands (maybe on an explicit user action?)
    logger.debug(f"Setting bot commands: {'; '.join(str(bc) for bc in bot_commands)}")
    for _, scoped_commands_it in itertools.groupby(
        sorted(
            bot_commands,
            key=BotCommandInfo.scope_key,
        ),
        key=BotCommandInfo.scope_key,
    ):
        command_info_batch = list(scoped_commands_it)
        logger.debug(f"Bot command batch: {'; '.join(str(bc) for bc in command_info_batch)}")
        try:
            async for attempt in rate_limit_retry():
                with attempt:
                    await bot.set_my_commands(
                        commands=[cmd.command for cmd in command_info_batch],
                        scope=command_info_batch[0].scope,
                    )
        except Exception:
            logger.exception("Error setting bot commands")

    if group_chat_discovery_handler is not None:
        group_chat_discovery_handler.setup_handlers(owner_id=owner_id, bot_id=bot_id, bot=bot)

    return BotRunner(
        bot_prefix=bot_prefix,
        bot=bot,
        background_jobs=background_jobs,
        aux_endpoints=aux_endpoints,
    )
