import datetime
import logging
import secrets
from pathlib import Path
from typing import Optional

from aiohttp import hdrs, web
from pydantic import BaseModel
from telebot import AsyncTeleBot
from telebot import types as tg
from telebot.runner import BotRunner
from telebot.types import service as tg_service
from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.stores.generic import KeyValueStore

from telebot_constructor.app_models import AuthType, LoggedInUser
from telebot_constructor.auth.auth import Auth
from telebot_constructor.constants import (
    TRUSTED_CLIENT_TOKEN_HEADER,
    TRUSTED_CLIENT_USER_ID_HEADER,
)
from telebot_constructor.static import static_file_content
from telebot_constructor.telegram_files_downloader import TelegramFilesDownloader
from telebot_constructor.utils.rate_limit_retry import rate_limit_retry

logger = logging.getLogger(__name__)


class TelegramUserData(BaseModel):
    id: int
    username: str | None
    full_name: str
    avatar_file_id: str | None

    @classmethod
    async def from_user(cls, bot: AsyncTeleBot, user: tg.User) -> "TelegramUserData":
        last_photo_file_id: None | str

        try:
            user_profile_photos = await bot.get_user_profile_photos(user.id, limit=1)
            last_photo: tg.PhotoSize = user_profile_photos.photos[0][0]  # type: ignore
            last_photo_file_id = last_photo.file_id
        except Exception:
            logger.info("Error getting user's profile pic, ignoring", exc_info=True)
            last_photo_file_id = None

        return TelegramUserData(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            avatar_file_id=last_photo_file_id,
        )


class TelegramAuth(Auth):
    STORE_PREFIX = "telegram-auth"

    def __init__(
        self,
        redis: RedisInterface,
        bot: AsyncTeleBot,
        telegram_files_downloader: TelegramFilesDownloader,
        bot_is_run_externally: bool = False,
        confirmation_timeout: datetime.timedelta = datetime.timedelta(minutes=10),
        access_token_lifetime: datetime.timedelta = datetime.timedelta(days=1),
        trusted_client_tokens: list[str] | None = None,
    ):
        self.bot = bot
        self.bot_username: Optional[str] = None
        self.telegram_files_downloader = telegram_files_downloader
        self.bot_is_run_externally = bot_is_run_externally
        self.trusted_client_tokens = trusted_client_tokens or []

        self.tg_user_data_by_access_code_store = KeyValueStore[TelegramUserData](
            name="tg-user-info",
            prefix=self.STORE_PREFIX,
            redis=redis,
            expiration_time=access_token_lifetime,
            dumper=TelegramUserData.model_dump_json,
            loader=TelegramUserData.model_validate_json,
        )
        self.access_token_by_start_param = KeyValueStore[str](
            name="access-token",
            prefix=self.STORE_PREFIX,
            redis=redis,
            expiration_time=confirmation_timeout,
            dumper=str,
            loader=str,
        )

    async def get_auth_user(self) -> tg.User:
        raise NotImplementedError()

    async def get_bot_username(self) -> str:
        if self.bot_username is None:
            try:
                async for attempt in rate_limit_retry():
                    with attempt:
                        bot_user = await self.bot.get_me()
                logger.info(f"Bot user loaded: {bot_user.to_json()}")
            except Exception:
                logger.exception("Error getting auth bot user, probably an invalid token")
                raise ValueError("Failed to get auth bot user with getMe, the token is probably invalid")
            if bot_user.username is None:
                raise ValueError("Bot username is not set, something's wrong!")
            self.bot_username = bot_user.username
        return self.bot_username

    def authenticate_from_trusted_client(self, request: web.Request) -> Optional[LoggedInUser]:
        if not self.trusted_client_tokens:
            return None
        token = request.headers.get(TRUSTED_CLIENT_TOKEN_HEADER)
        if not token or token not in self.trusted_client_tokens:
            return None
        tg_user_id_str = request.headers.get(TRUSTED_CLIENT_USER_ID_HEADER)
        if not tg_user_id_str:
            return None
        try:
            tg_user_id = int(tg_user_id_str)
        except Exception:
            return None
        return LoggedInUser(
            auth_type=AuthType.TELEGRAM_AUTH,
            username=user_id(tg_user_id),
            name="<unused>",
            display_username="<unused>",
            userpic=None,
        )

    ACCESS_TOKEN_COOKIE_NAME = "tc_access_token"

    async def authenticate_request(self, request: web.Request) -> Optional[LoggedInUser]:
        if user := self.authenticate_from_trusted_client(request):
            return user
        access_token = request.cookies.get(self.ACCESS_TOKEN_COOKIE_NAME)
        if access_token is None:
            logger.info("No auth cookie found in the request")
            return None
        tg_user_data = await self.tg_user_data_by_access_code_store.load(access_token)
        if tg_user_data is None:
            logger.info("Invalid access token")
            return None
        logger.info("Auth OK")
        return LoggedInUser(
            auth_type=AuthType.TELEGRAM_AUTH,
            username=user_id(tg_user_data.id),
            name=tg_user_data.full_name,
            display_username=tg_user_data.username,
            userpic=(
                None
                if tg_user_data.avatar_file_id is None
                else await self.telegram_files_downloader.get_base64_file(self.bot, tg_user_data.avatar_file_id)
            ),
        )

    async def unauthenticated_client_response(self, request: web.Request, static_files_dir: Path) -> web.Response:
        return web.Response(
            body=static_file_content(static_files_dir / "telegram_auth_login.html"),
            content_type="text/html",
        )

    async def setup_routes(self, app: web.Application) -> None:
        async def try_login(request: web.Request) -> web.Response:
            try:
                request_json = await request.json()
                bot_start_param = request_json["bot_start_param"]
            except KeyError:
                raise web.HTTPBadRequest(reason="Required `bot_start_param` field not present in request body")
            except Exception:
                raise web.HTTPBadRequest(reason="Request body must be a valid JSON object")
            access_token = await self.access_token_by_start_param.load(bot_start_param)
            if access_token is None:
                logger.info("Invalid bot start param submitted to /try-login")
                raise web.HTTPNotFound()
            if not await self.tg_user_data_by_access_code_store.exists(access_token):
                logger.info("Tg user not yet recorded for the access token")
                raise web.HTTPNotFound()
            logger.info("Associated TG user with access code, returning to the client")
            return web.Response(
                text="OK",
                headers={hdrs.SET_COOKIE: f"{self.ACCESS_TOKEN_COOKIE_NAME}={access_token}; Path=/"},
            )

        app.router.add_post("/telegram-auth/try-login", try_login)

        async def request_auth_link(request: web.Request) -> web.Response:
            start_param = secrets.token_hex(16)
            bot_username = await self.get_bot_username()
            access_token = secrets.token_hex(32)
            await self.access_token_by_start_param.save(start_param, access_token)
            return web.Response(text=f"https://t.me/{bot_username}?start={start_param}")

        # NOTE: DDoS posibility? add rate limiting by IP?
        app.router.add_post("/telegram-auth/make-auth-link", request_auth_link)

    async def setup_bot(self) -> Optional[BotRunner]:
        @self.bot.message_handler(commands=["start"], priority=100)
        async def save_telegram_user_data(message: tg.Message):
            continue_ = tg_service.HandlerResult(continue_to_other_handlers=True)
            message_text_parts = message.text_content.split()
            if len(message_text_parts) <= 1:
                return continue_
            start_param = message_text_parts[1]
            access_token = await self.access_token_by_start_param.load(start_param)
            if access_token is None:
                return continue_
            user = message.from_user
            tg_user_data = await TelegramUserData.from_user(self.bot, message.from_user)
            await self.tg_user_data_by_access_code_store.save(access_token, tg_user_data)

            formatted_user = user.full_name
            if user.username:
                formatted_user += f" @{user.username}"
            await self.bot.reply_to(
                message,
                text=f"Вы авторизованы как <b>{formatted_user}</b>! Можно вернуться в конструктор.",
                parse_mode="HTML",
            )
            return continue_

        if self.bot_is_run_externally:
            return None
        else:
            return BotRunner(bot_prefix="telegram-auth-bot", bot=self.bot, background_jobs=[])

    def owner_chat_id(self, user_id: str) -> int:
        return parse_tg_user_id(user_id)


def user_id(tg_user_id: int) -> str:
    return f"telegram_user_{tg_user_id}"


def parse_tg_user_id(user_id: str) -> int:
    return int(user_id.removeprefix("telegram_user_"))
