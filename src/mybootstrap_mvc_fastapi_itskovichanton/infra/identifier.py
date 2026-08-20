"""Парсинг единого поля identifier: email или телефон."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import phonenumbers
from email_validator import EmailNotValidError, validate_email
from phonenumbers import NumberParseException


class IdentifierType(StrEnum):
    EMAIL = "email"
    PHONE = "phone"


@dataclass(frozen=True)
class ParsedIdentifier:
    type: IdentifierType
    value: str  # email lower / phone E.164
    raw: str


def parse_identifier(raw: str, *, default_region: str = "RU") -> ParsedIdentifier:
    """
    Определяет email или телефон.
    Телефон нормализуется в E.164 (+7...).
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("Пустой identifier")

    # Явный email
    if "@" in text:
        try:
            info = validate_email(text, check_deliverability=False)
            return ParsedIdentifier(IdentifierType.EMAIL, info.normalized.lower(), text)
        except EmailNotValidError as e:
            raise ValueError(f"Некорректный email: {e}") from e

    # Телефон
    try:
        num = phonenumbers.parse(text, default_region)
        if not phonenumbers.is_possible_number(num) or not phonenumbers.is_valid_number(num):
            raise ValueError("Некорректный номер телефона")
        e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
        return ParsedIdentifier(IdentifierType.PHONE, e164, text)
    except NumberParseException as e:
        raise ValueError(f"Некорректный identifier: {e}") from e


def mask_identifier(parsed: ParsedIdentifier) -> str:
    """Маска для UI / логов."""
    if parsed.type == IdentifierType.EMAIL:
        local, _, domain = parsed.value.partition("@")
        if len(local) <= 2:
            return f"*@{domain}"
        return f"{local[0]}***{local[-1]}@{domain}"
    # +79991234567 → +7 (999) ***-**-67
    digits = parsed.value
    if len(digits) >= 4:
        return f"{digits[:2]} ({digits[2:5]}) ***-**-{digits[-2:]}"
    return "***"
