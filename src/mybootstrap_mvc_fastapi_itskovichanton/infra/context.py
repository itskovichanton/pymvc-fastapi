"""Контекст запроса: request_id из asgi-correlation-id (+ локальный fallback)."""

from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4

_request_id: ContextVar[str | None] = ContextVar("mvc_request_id", default=None)
_service_name: ContextVar[str | None] = ContextVar("mvc_service_name", default=None)


def get_request_id() -> str | None:
    try:
        from asgi_correlation_id.context import correlation_id

        rid = correlation_id.get()
        if rid:
            return rid
    except ImportError:
        pass
    return _request_id.get()


def set_request_id(value: str | None) -> None:
    _request_id.set(value)
    try:
        from asgi_correlation_id.context import correlation_id

        correlation_id.set(value)
    except ImportError:
        pass


def ensure_request_id() -> str:
    rid = get_request_id()
    if not rid:
        rid = str(uuid4())
        set_request_id(rid)
    return rid


def get_service_name() -> str | None:
    return _service_name.get()


def set_service_name(value: str | None) -> None:
    _service_name.set(value)
