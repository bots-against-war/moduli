import asyncio
import logging
import time
import traceback
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import pydantic
from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.stores.generic import KeyListStore, KeyValueStore

from telebot_constructor.constants import CONSTRUCTOR_PREFIX
from telebot_constructor.utils import page_params_to_redis_indices

logger = logging.getLogger(__name__)


class BotError(pydantic.BaseModel):
    timestamp: float
    message: str  # message used in logger.error("some message")
    exc_type: str | None = None  # "KeyError", "ValueError", etc
    exc_traceback: str | None = None  # multiline string with exception traceback

    @classmethod
    def from_log_record(cls, record: logging.LogRecord) -> "BotError":
        try:
            exc_type_str: str | None = record.exc_info[0].__name__  # type: ignore
        except Exception:
            exc_type_str = None

        try:
            exc_traceback: str | None = "\n".join(traceback.format_tb(record.exc_info[2]))  # type: ignore
        except Exception:
            exc_traceback = None

        return BotError(
            timestamp=time.time(),
            message=record.getMessage(),
            exc_type=exc_type_str,
            exc_traceback=exc_traceback,
        )


class _LogHandler(logging.Handler):
    def __init__(self, store: "BotErrorsStore", owner_id: str, bot_id: str) -> None:
        logging.Handler.__init__(self, level=logging.ERROR)
        self._store = store
        self._owner_id = owner_id
        self._bot_id = bot_id
        self._tasks: set[asyncio.Task[Any]] = set()

    def emit(self, record: Any) -> None:
        if not isinstance(record, logging.LogRecord):
            return
        task = asyncio.create_task(
            self._store.process_error(
                owner_id=self._owner_id,
                bot_id=self._bot_id,
                error=BotError.from_log_record(record),
            )
        )
        task.add_done_callback(self._tasks.discard)
        self._tasks.add(task)


@dataclass
class BotErrorContext:
    owner_id: str
    bot_id: str
    alert_chat_id: int | str
    error: BotError


BotErrorCallback = Callable[[BotErrorContext], Awaitable[Any]]


class BotErrorsStore:
    STORE_PREFIX = f"{CONSTRUCTOR_PREFIX}/errors"

    def __init__(self, redis: RedisInterface) -> None:
        self._bot_errors_store = KeyListStore[BotError](
            name="errors",
            prefix=self.STORE_PREFIX,
            redis=redis,
            expiration_time=None,
            loader=BotError.model_validate_json,
            dumper=BotError.model_dump_json,
        )
        self._alert_chat_store = KeyValueStore[str | int](
            name="alert-chat",
            prefix=self.STORE_PREFIX,
            redis=redis,
            expiration_time=None,
        )
        self.error_callback: BotErrorCallback | None = None

    def _composite_key(self, owner_id: str, bot_id: str) -> str:
        return f"{owner_id}/{bot_id}"

    def adapter_for(self, owner_id: str, bot_id: str) -> "BotSpecificErrorsStore":
        return BotSpecificErrorsStore(
            store=self,
            owner_id=owner_id,
            bot_id=bot_id,
        )

    async def process_error(self, owner_id: str, bot_id: str, error: BotError) -> None:
        try:
            key = self._composite_key(owner_id, bot_id)
            await self._bot_errors_store.push(key, error)
            if self.error_callback is not None:
                alert_chat_id = await self._alert_chat_store.load(key)
                if alert_chat_id is not None:
                    await self.error_callback(
                        BotErrorContext(
                            owner_id=owner_id,
                            bot_id=bot_id,
                            alert_chat_id=alert_chat_id,
                            error=error,
                        )
                    )
        except Exception:
            logger.exception(f"Error processing error: {owner_id=} {bot_id=} {error=}")

    def instrument(self, li: logging.Logger, owner_id: str, bot_id: str) -> None:
        li.addHandler(_LogHandler(store=self, owner_id=owner_id, bot_id=bot_id))

    async def load_errors(self, username: str, bot_id: str, offset: int, count: int) -> list[BotError]:
        start, end = page_params_to_redis_indices(offset, count)
        return (
            await self._bot_errors_store.slice(
                key=self._composite_key(username, bot_id),
                start=start,
                end=end,
            )
            or []
        )

    async def load_alert_chat_id(self, owner_id: str, bot_id: str) -> int | str | None:
        return await self._alert_chat_store.load(key=self._composite_key(owner_id, bot_id))

    async def save_alert_chat_id(self, owner_id: str, bot_id: str, chat_id: int | str) -> bool:
        return await self._alert_chat_store.save(key=self._composite_key(owner_id, bot_id), value=chat_id)


@dataclass
class BotSpecificErrorsStore:
    store: BotErrorsStore
    owner_id: str
    bot_id: str

    def instrument(self, logger: logging.Logger) -> None:
        self.store.instrument(logger, owner_id=self.owner_id, bot_id=self.bot_id)
