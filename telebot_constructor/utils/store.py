import dataclasses
import datetime
import json
from typing import Any, Callable, Generic, Mapping

from telebot_components.stores.generic import KeyValueStore, PrefixedStore, ValueT, str_able

_CACHE = dict[str, Any]()


@dataclasses.dataclass
class CachedKeyValueStore(PrefixedStore, Generic[ValueT]):
    """
    Like KeyValueStore, but caches everything in memory for faster repeated reads.
    The cache is *never* invalidated, so it's suitable mostly for immutable stores.
    """

    dumper: Callable[[ValueT], str] = json.dumps
    loader: Callable[[str], ValueT] = json.loads
    expiration_time: datetime.timedelta | None = None

    def __post_init__(self):
        super().__post_init__()
        self._persistent = KeyValueStore[ValueT](
            name=self.name,
            prefix=self.prefix,
            redis=self.redis,
            expiration_time=self.expiration_time,
            dumper=self.dumper,
            loader=self.loader,
        )

    async def save(self, key: str_able, value: ValueT) -> bool:
        _CACHE[self._full_key(key)] = value
        return await self._persistent.save(key, value)

    async def save_multiple(self, mapping: Mapping[str, ValueT]) -> bool:
        for key, value in mapping.items():
            _CACHE[self._full_key(key)] = value
        return await self._persistent.save_multiple(mapping)

    async def load(self, key: str_able) -> ValueT | None:
        full_key = self._full_key(key)
        if cached := _CACHE.get(full_key):
            return cached  # type: ignore
        from_store = await self._persistent.load(key)
        if from_store is not None:
            _CACHE[full_key] = from_store
        return from_store
