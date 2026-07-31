"""Language detection helpers for localized interface text assertions."""

from __future__ import annotations

import re
from enum import Enum
from typing import Iterable


_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN = re.compile(r"[A-Za-z]")


class TextLanguage(str, Enum):
    CHINESE = "zh-CN"
    ENGLISH = "en"
    MIXED = "mixed"
    UNKNOWN = "unknown"


def detect_text_language(value: str) -> TextLanguage:
    """Classify text from its Han and Latin letters; digits/punctuation are neutral."""
    if not isinstance(value, str) or not value.strip():
        return TextLanguage.UNKNOWN
    has_han = _HAN.search(value) is not None
    has_latin = _LATIN.search(value) is not None
    if has_han and has_latin:
        return TextLanguage.MIXED
    if has_han:
        return TextLanguage.CHINESE
    if has_latin:
        return TextLanguage.ENGLISH
    return TextLanguage.UNKNOWN


def is_text_in_language(value: str, expected: str | TextLanguage) -> bool:
    """Accept mixed identifiers as Chinese when they contain meaningful Han text."""
    expected_language = TextLanguage(expected)
    actual = detect_text_language(value)
    if expected_language is TextLanguage.CHINESE:
        return actual in {TextLanguage.CHINESE, TextLanguage.MIXED}
    if expected_language is TextLanguage.ENGLISH:
        return actual is TextLanguage.ENGLISH
    return actual is expected_language


def assert_texts_in_language(values: Iterable[str], expected: str | TextLanguage) -> None:
    """Assert every supplied localized name is non-empty and matches the language."""
    expected_language = TextLanguage(expected)
    names = list(values)
    if not names:
        raise AssertionError("响应中没有采集到 needTransName 名称字段")
    mismatches = [
        (name, detect_text_language(name).value)
        for name in names
        if not is_text_in_language(name, expected_language)
    ]
    if mismatches:
        rendered = ", ".join(f"{name!r}（识别为 {actual}）" for name, actual in mismatches)
        raise AssertionError(f"名称字段应为 {expected_language.value}: {rendered}")
