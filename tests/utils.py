import datetime
import time
from typing import Any, Callable, Optional, TypeVar

from cryptography.fernet import Fernet
from telebot import types as tg
from telebot.metrics import TelegramUpdateMetrics
from telebot.test_util import MethodCall
from telebot.types import Dictionaryable
from telebot_components.redis_utils.emulation import RedisEmulation
from telebot_components.redis_utils.interface import RedisInterface
from telebot_components.utils.secrets import RedisSecretStore, SecretStore
from typing_extensions import TypeGuard

from telebot_constructor.store.errors import BotErrorsStore, BotSpecificErrorsStore
from telebot_constructor.store.form_results import (
    BotSpecificFormResultsStore,
    FormResultsStore,
)


def dummy_secret_store(redis: RedisInterface) -> SecretStore:
    return RedisSecretStore(
        redis,
        encryption_key=Fernet.generate_key().decode("utf-8"),
        secrets_per_user=100,
        secret_max_len=1000,
        scope_secrets_to_user=True,
    )


def tg_update_message_to_bot(
    user_id: int,
    first_name: str,
    text: str,
    group_chat_id: Optional[int] = None,
    user_kwargs: dict[str, Any] | None = None,
    metrics: Optional[TelegramUpdateMetrics] = None,
) -> tg.Update:
    return tg.Update(
        update_id=1,
        message=tg.Message(
            message_id=1,
            from_user=tg.User(id=user_id, is_bot=False, first_name=first_name, **(user_kwargs or {})),
            date=int(time.time()),
            chat=(
                tg.Chat(id=user_id, type="private", first_name=first_name)
                if group_chat_id is None
                else tg.Chat(
                    id=group_chat_id,
                    title="group chat",
                    type="supergroup",
                )
            ),
            content_type="text",
            options={"text": text},
            json_string="",
        ),
        edited_message=None,
        channel_post=None,
        edited_channel_post=None,
        inline_query=None,
        chosen_inline_result=None,
        callback_query=None,
        shipping_query=None,
        pre_checkout_query=None,
        poll=None,
        poll_answer=None,
        my_chat_member=None,
        chat_member=None,
        chat_join_request=None,
        metrics=metrics,
        _json_dict={},
    )


def tg_update_callback_query(user_id: int, first_name: str, callback_query: str) -> tg.Update:
    return tg.Update(
        update_id=1,
        message=None,
        edited_message=None,
        channel_post=None,
        edited_channel_post=None,
        inline_query=None,
        chosen_inline_result=None,
        callback_query=tg.CallbackQuery(
            id=123456,
            from_user=tg.User(id=user_id, is_bot=False, first_name=first_name),
            data=callback_query,
            chat_instance=None,
            json_string=None,
            message=tg.Message(
                message_id=1,
                from_user=tg.User(id=user_id, is_bot=False, first_name=first_name),
                date=int(time.time()),
                chat=tg.Chat(id=user_id, type="private", first_name=first_name),
                content_type="text",
                options={},
                json_string="",
            ),
        ),
        shipping_query=None,
        pre_checkout_query=None,
        poll=None,
        poll_answer=None,
        my_chat_member=None,
        chat_member=None,
        chat_join_request=None,
        _json_dict={},
    )


def assert_dict_includes(actual: dict, included: dict) -> None:
    """Actual dict is allowed to have extra keys beyond those required"""
    for required_key, required_value in included.items():
        assert required_key in actual, f"{actual} misses required key {required_key!r}"
        assert actual[required_key] == required_value, (
            f"{actual} contains {required_key!r}: {actual[required_key]} != {required_value}"
        )


def assert_dicts_include(actual_dicts: list[dict], required_subdicts: list[dict]) -> None:
    assert len(actual_dicts) == len(required_subdicts), (
        f"actual dicts list has mismatching size: {len(actual_dicts)} != {len(required_subdicts)}: "
        + f"{actual_dicts=}, {required_subdicts=}"
    )
    for actual, required in zip(actual_dicts, required_subdicts):
        assert_dict_includes(actual, required)


def assert_method_call_kwargs_include(method_calls: list[MethodCall], required_call_kwargs: list[dict]) -> None:
    call_kwargs = [mc.full_kwargs for mc in method_calls]
    assert_dicts_include(call_kwargs, required_call_kwargs)


def _dictify_method_call_kwargs(d: Any) -> Any:
    """Convert"""
    if isinstance(d, dict):
        return {k: _dictify_method_call_kwargs(v) for k, v in d.items()}
    elif isinstance(d, list):
        return [_dictify_method_call_kwargs(el) for el in d]
    elif isinstance(d, tg.InputMedia):
        media_json, files = d.convert_input_media()
        return {"media_json": media_json, "files": files}
    elif isinstance(d, Dictionaryable):
        return d.to_dict()
    else:
        return d


def assert_method_call_dictified_kwargs_include(
    method_calls: list[MethodCall], required_call_kwargs: list[dict]
) -> None:
    assert_dicts_include(_dictify_method_call_kwargs([mc.full_kwargs for mc in method_calls]), required_call_kwargs)


def dummy_form_results_store() -> BotSpecificFormResultsStore:
    return FormResultsStore(RedisEmulation()).adapter_for(owner_id="dummy", bot_id="dummy")


def dummy_errors_store() -> BotSpecificErrorsStore:
    return BotErrorsStore(RedisEmulation()).adapter_for(owner_id="dummy", bot_id="dummy")


DataT = TypeVar("DataT")


def mask_recursively(
    data: DataT,
    predicate: Callable[[Any], bool],
    mask: Callable[[Any], str],
) -> DataT | str:
    if predicate(data):
        return mask(data)
    elif isinstance(data, dict):
        return {k: mask_recursively(v, predicate, mask) for k, v in data.items()}  # type: ignore
    elif isinstance(data, list):
        return [mask_recursively(item, predicate, mask) for item in data]  # type: ignore
    else:
        return data


RECENT_TIMESTAMP = "<recent timestamp>"
SMALL_TIME_DURATION = "<small time duration>"


def mask_recent_timestamps(data: DataT) -> DataT | str:
    def looks_like_recent_timestamp(value: Any) -> TypeGuard[float]:
        if not isinstance(value, float):
            return False
        try:
            dt = datetime.datetime.fromtimestamp(value)
        except Exception:
            return False
        now = datetime.datetime.now()
        return dt < now and now - dt < datetime.timedelta(minutes=1)

    return mask_recursively(data, predicate=looks_like_recent_timestamp, mask=lambda _: RECENT_TIMESTAMP)


def mask_small_time_durations(data: DataT) -> DataT | str:
    def looks_like_small_time_duration(v: Any) -> bool:
        return isinstance(v, float) and 0 < v < 0.1

    return mask_recursively(data, predicate=looks_like_small_time_duration, mask=lambda _: SMALL_TIME_DURATION)
