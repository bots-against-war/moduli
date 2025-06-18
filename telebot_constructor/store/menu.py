import datetime
import hashlib
from typing import Any

import pydantic
from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.stores.generic import KeyListStore

from telebot_constructor.utils.store import CachedKeyValueStore


class ButtonActionData(pydantic.BaseModel):
    block_id: str
    route_to_block_id: str | None  # None = back button, popping block id from history

    def model_post_init(self, context: Any) -> None:
        self._md5_hash = hashlib.md5(self.model_dump_json().encode("utf-8")).hexdigest()

    @property
    def md5_hash(self) -> str:
        return self._md5_hash


class MenuMetadataStore:
    def __init__(self, redis: RedisInterface, bot_prefix: str) -> None:
        self.button_action_store = CachedKeyValueStore[ButtonActionData](
            name="button-action",
            prefix=bot_prefix,
            redis=redis,
            dumper=ButtonActionData.model_dump_json,
            loader=ButtonActionData.model_validate_json,
            expiration_time=datetime.timedelta(days=180),
        )
        self.user_history_store = KeyListStore[str](
            name="menu-history",
            prefix=bot_prefix,
            redis=redis,
            expiration_time=datetime.timedelta(days=180),
            dumper=str,
            loader=str,
        )
