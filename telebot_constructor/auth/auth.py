import abc
import datetime
import logging
import secrets
from pathlib import Path
from typing import Optional

from aiohttp import hdrs, web
from telebot import AsyncTeleBot
from telebot import types as tg
from telebot.runner import BotRunner
from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.stores.generic import KeyValueStore

from telebot_constructor.app_models import AuthType, LoggedInUser
from telebot_constructor.static import static_file_content
from telebot_constructor.telegram_files_downloader import TelegramFilesDownloader


class Auth(abc.ABC):
    """Interface class for different ways to authenticate web requests"""

    @abc.abstractmethod
    async def authenticate_request(self, request: web.Request) -> Optional[LoggedInUser]:
        """Request authentication, must return details on logged-in user"""
        ...

    @abc.abstractmethod
    async def unauthenticated_client_response(self, request: web.Request, static_files_dir: Path) -> web.Response:
        """Auth-specific response to the client; not used for API routes, only for browser clients"""
        ...

    @abc.abstractmethod
    def owner_chat_id(self, user_id: str) -> int:
        """Telegram chat somehow associated with an authorized user"""
        ...

    async def setup_routes(self, app: web.Application) -> None:
        """Optional setup hook for subclasses to override to add their login API routes"""
        ...

    async def setup_bot(self) -> BotRunner | None:
        """Optional setup hook for subclasses to create a service auth bot that will be run with the app"""
        ...


class NoAuth(Auth):
    """
    Dummy auth that lets anyone use the constructor and all of it's bots.
    Useful when running in a private network or during development.
    """

    def __init__(
        self,
        owner_chat_id: int,
        username: str = "no-auth",
    ) -> None:
        self._user_id = username
        self._owner_chat_id = owner_chat_id

    async def authenticate_request(self, request: web.Request) -> Optional[LoggedInUser]:
        return LoggedInUser(
            username=self._user_id,
            name="Anonymous user",
            auth_type=AuthType.NO_AUTH,
            userpic=None,
        )

    def owner_chat_id(self, user_id: str) -> int:
        return self._owner_chat_id

    async def unauthenticated_client_response(self, request: web.Request, static_files_dir: Path) -> web.Response:
        raise NotImplementedError()


class GroupChatAuth(Auth):
    """
    Telegram group chat based auth. You need to have a bot and a group chat it can send messages to.
    Everyone in the group chat will have shared access to the constructor.
    """

    CONST_KEY = "const"
    STORE_PREFIX = "group-chat-auth"

    def __init__(
        self,
        redis: RedisInterface,
        bot: AsyncTeleBot,
        auth_chat_id: int,
        telegram_files_downloader: TelegramFilesDownloader,
        confirmation_code_lifetime: datetime.timedelta = datetime.timedelta(minutes=10),
        access_token_lifetime: datetime.timedelta = datetime.timedelta(days=1),
    ):
        self.bot = bot
        self.auth_chat_id = auth_chat_id
        self._auth_chat: Optional[tg.Chat] = None  # fetched lazily
        self.logger = logging.getLogger(__name__ + f"[{self.__class__.__name__}]")
        self.telegram_files_downloader = telegram_files_downloader

        self.access_code_store = KeyValueStore[str](
            name="access-code",
            prefix=self.STORE_PREFIX,
            redis=redis,
            expiration_time=confirmation_code_lifetime,
            dumper=lambda x: x,
            loader=lambda x: x,
        )
        self.access_tokens_store = KeyValueStore[None](
            name="access-tokens",
            prefix=self.STORE_PREFIX,
            redis=redis,
            expiration_time=access_token_lifetime,
            dumper=lambda x: "null",
            loader=lambda x: None,
        )

    def owner_chat_id(self, user_id: str) -> int:
        return self.auth_chat_id

    async def get_auth_chat(self) -> tg.Chat:
        if self._auth_chat is None:
            chat = await self.bot.get_chat(chat_id=self.auth_chat_id)
            self._auth_chat = chat
        return self._auth_chat

    ACCESS_TOKEN_COOKIE_NAME = "tc_access_token"

    async def authenticate_request(self, request: web.Request) -> Optional[LoggedInUser]:
        token = request.cookies.get(self.ACCESS_TOKEN_COOKIE_NAME)
        if token is None:
            self.logger.info("No auth cookie found in request")
            return None
        if not (await self.access_tokens_store.exists(token)):
            self.logger.info("Invalid auth cookie in request")
            return None
        self.logger.info("Auth OK")
        auth_chat = await self.get_auth_chat()
        return LoggedInUser(
            username="admin",
            name=f"Anonymous auth chat member (via {auth_chat.title or 'chat id ' + str(auth_chat.id)})",
            auth_type=AuthType.TELEGRAM_GROUP_AUTH,
            userpic=(
                None
                if auth_chat.photo is None
                else (await self.telegram_files_downloader.get_base64_file(self.bot, auth_chat.photo.small_file_id))
            ),
        )

    async def unauthenticated_client_response(self, request: web.Request, static_files_dir: Path) -> web.Response:
        return web.Response(
            body=static_file_content(static_files_dir / "group_chat_auth_login.html"),
            content_type="text/html",
        )

    async def setup_routes(self, app: web.Application) -> None:
        async def login(request: web.Request) -> web.Response:
            try:
                request_json = await request.json()
                code = request_json["code"]
            except KeyError:
                raise web.HTTPBadRequest(reason="Required `code` field not present in request body")
            except Exception:
                raise web.HTTPBadRequest(reason="Request body must be a valid JSON object")
            correct_code = await self.access_code_store.load(self.CONST_KEY)
            if correct_code != code:
                self.logger.info("Invalid confirmation code submitted")
                raise web.HTTPUnauthorized()
            access_token = secrets.token_hex(nbytes=32)
            self.logger.info("Confirmation code OK, issuing access token")
            if not await self.access_tokens_store.save(access_token, None):
                raise web.HTTPInternalServerError()
            return web.Response(
                text="OK", headers={hdrs.SET_COOKIE: f"{self.ACCESS_TOKEN_COOKIE_NAME}={access_token}; Path=/"}
            )

        app.router.add_post("/group-chat-auth/login", login)

        async def request_confirmation_code(request: web.Request) -> web.Response:
            if not (await self.access_code_store.exists(self.CONST_KEY)):
                access_code = secrets.token_hex(16)
                await self.access_code_store.save(self.CONST_KEY, access_code)
                await self.bot.send_message(
                    chat_id=self.auth_chat_id,
                    text=f"🔑🔑🔑\n\nModuli access code\n\n<pre>{access_code}</pre>",
                    parse_mode="HTML",
                )
            return web.Response(text="OK", status=200)

        app.router.add_post("/group-chat-auth/request-confirmation-code", request_confirmation_code)
