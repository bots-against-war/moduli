import logging
import time
from dataclasses import dataclass

import aiohttp
from multidict import istr
from telebot import types as tg

from telebot_constructor.app_models import (
    BotTokenValidationResult,
    SaveBotConfigVersionPayload,
)
from telebot_constructor.constants import (
    TRUSTED_CLIENT_TOKEN_HEADER,
    TRUSTED_CLIENT_USER_ID_HEADER,
)

logger = logging.getLogger(__name__)


@dataclass
class TrustedModuliApiClientConfig:
    base_url: str
    trusted_client_token: str


@dataclass
class TrustedModuliApiClient:
    aiohttp_session: aiohttp.ClientSession
    config: TrustedModuliApiClientConfig

    def auth_headers(self, user: tg.User) -> dict[istr, str]:
        return {
            TRUSTED_CLIENT_TOKEN_HEADER: self.config.trusted_client_token,
            TRUSTED_CLIENT_USER_ID_HEADER: str(user.id),
        }

    def api_url(self, path: str) -> str:
        base = self.config.base_url.rstrip("/")
        path = path.lstrip("/")
        return "/".join((base, "api", path))

    async def ping(self) -> None:
        start = time.time()
        async with self.aiohttp_session.get(self.api_url("/ping")) as resp:
            text = await resp.text()
            logger.info(f"Got response: {text} ({resp.status})")
        logger.info(f"moduli API pinged in {time.time() - start:.3f} sec")

    async def validate_token(self, user: tg.User, token: str) -> BotTokenValidationResult | None:
        async with self.aiohttp_session.post(
            self.api_url("/validate-token"),
            headers=self.auth_headers(user),
            json={"token": token},
        ) as resp:
            if resp.ok:
                return BotTokenValidationResult.model_validate_json(await resp.text())
            else:
                logger.info(f"Token validation error: {await resp.text()}")
                return None

    async def create_token_secret(self, user: tg.User, name: str, value: str) -> bool:
        async with self.aiohttp_session.post(
            self.api_url(f"/secrets/{name}?is_token=true"),
            headers=self.auth_headers(user),
            data=value,
        ) as resp:
            return resp.ok

    async def save_and_start_bot(self, user: tg.User, bot_id: str, payload: SaveBotConfigVersionPayload) -> bool:
        async with self.aiohttp_session.post(
            self.api_url(f"/config/{bot_id}"),
            headers=self.auth_headers(user),
            json=payload.model_dump(mode="json"),
        ) as resp:
            return resp.ok
