from typing import Any, Self, Union, get_args, get_origin

from pydantic import (
    BaseModel,
    BeforeValidator,
    ModelWrapValidatorHandler,
    PlainSerializer,
    WithJsonSchema,
    model_validator,
)
from telebot_components.language import LanguageData
from typing_extensions import Annotated


class ExactlyOneNonNullFieldModel(BaseModel):
    """
    If a subclass model has several Optional[...] fields, exactly one of them must contain the actual value,
    and others be None.

    Useful for modelling a union of different types under one wrapper object, like how Telegram Bot API
    handles multiple possible kinds of Update (https://core.telegram.org/bots/api#getting-updates)
    """

    @model_validator(mode="wrap")
    @classmethod
    def validate_exactly_one_non_null_field(cls, data: Any, handler: ModelWrapValidatorHandler[Self]) -> Self:
        instance = handler(data)
        optional_field_names: set[str] = set()
        for field_name, field_info in cls.model_fields.items():
            if get_origin(field_info.annotation) == Union and type(None) in get_args(field_info.annotation):
                optional_field_names.add(field_name)
        non_null_optional_fields = {name for name in optional_field_names if getattr(instance, name) is not None}
        if len(non_null_optional_fields) != 1:
            raise ValueError(
                f"Exacly one optional field (of {sorted(optional_field_names)}) must be set to a non-null value, "
                + f"but {len(non_null_optional_fields)} actually are: {sorted(non_null_optional_fields)}"
            )
        return instance


def _parse_language_data(code: Any) -> LanguageData:
    if isinstance(code, LanguageData):
        return code
    if not isinstance(code, str):
        raise ValueError("language code is expected to be a string containing IETF language tag")
    try:
        return LanguageData.lookup(code)
    except Exception:
        raise ValueError("unknown language code")


# LanguageData used by telebot_components, annotated with pydantic stuff to expose it in API
Language = Annotated[
    LanguageData,
    BeforeValidator(_parse_language_data),
    PlainSerializer(lambda lang_data: lang_data.code, return_type=str),
    WithJsonSchema({"type": "string", "format": "IETF-language-tag"}, mode="serialization"),
    WithJsonSchema({"type": "string", "format": "IETF-language-tag"}, mode="validation"),
]

MultilangText = dict[Language, str]

# AKA AnyText in telebot_components, here renamed to clearly mark strings that allow localization
LocalizableText = Union[str, MultilangText]
