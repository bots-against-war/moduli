import logging
import time
from dataclasses import dataclass

import aiohttp
from multidict import istr
from telebot import types as tg

from telebot_constructor.app_models import SaveBotConfigVersionPayload
from telebot_constructor.constants import (
    TRUSTED_CLIENT_TOKEN_HEADER,
    TRUSTED_CLIENT_USER_ID_HEADER,
)

logger = logging.getLogger(__name__)


@dataclass
class TrustedModuliApiClient:
    aiohttp_session: aiohttp.ClientSession
    base_url: str
    trusted_client_token: str

    def auth_headers(self, user: tg.User) -> dict[istr, str]:
        return {
            TRUSTED_CLIENT_TOKEN_HEADER: self.trusted_client_token,
            TRUSTED_CLIENT_USER_ID_HEADER: str(user.id),
        }

    def api_url(self, path: str) -> str:
        base = self.base_url.rstrip("/")
        path = path.lstrip("/")
        return "/".join((base, "api", path))

    async def ping(self) -> None:
        start = time.time()
        async with self.aiohttp_session.get(self.api_url("/ping")) as resp:
            text = await resp.text()
            logger.info(f"Got response: {text} ({resp.status})")
        logger.info(f"moduli API pinged in {time.time() - start:.3f} sec")

    async def create_secret(self, user: tg.User, name: str, value: str) -> bool:
        async with self.aiohttp_session.post(
            self.api_url(f"/secrets/{name}"),
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
