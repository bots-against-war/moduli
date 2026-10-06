from typing import Optional

import pydantic
import pytest
from pydantic import BaseModel, ValidationError
from telebot_components.language import LanguageData

from telebot_constructor.utils.pydantic import ExactlyOneNonNullFieldModel, Language


def test_exactly_one_non_null_field_model() -> None:
    class Example(ExactlyOneNonNullFieldModel):
        number: int
        foo: Optional[str] = None
        bar: Optional[int] = None
        baz: Optional[bool] = None

    # valid instantiations
    Example(number=1, foo="hello")
    Example(number=2, bar=1312)
    Example(number=3, baz=True)

    # invalid instantiations
    with pytest.raises(ValidationError):
        Example(number=4, foo="world", bar=111)
    with pytest.raises(ValidationError):
        Example(number=4, foo="world", baz=False)
    with pytest.raises(ValidationError):
        Example(number=4, bar=111, baz=True)
    with pytest.raises(ValidationError):
        Example(number=4, foo="world", bar=111, baz=False)


class LanguageContainer(BaseModel):
    lang: Language


def test_languge_json_schema() -> None:
    assert LanguageContainer.model_json_schema()["properties"] == {
        "lang": {"format": "IETF-language-tag", "type": "string"}
    }


@pytest.mark.parametrize(
    "code",
    [
        "en",
        "ru",
        "hy",
        "ar",
    ],
)
def test_language_type_ok(code: str) -> None:
    class LanguageContainer(BaseModel):
        lang: Language

    container = LanguageContainer(**{"lang": code})  # type: ignore
    assert isinstance(container.lang, LanguageData)
    assert container.model_dump() == {"lang": code}


@pytest.mark.parametrize(
    "code",
    ["", "abcajdhf", 1, None],
)
def test_language_type_invalid(code: str) -> None:
    with pytest.raises(
        pydantic.ValidationError,
        match="1 validation error for LanguageContainer\nlang\n  Value error",
    ):
        _container = LanguageContainer(**{"lang": code})  # type: ignore
