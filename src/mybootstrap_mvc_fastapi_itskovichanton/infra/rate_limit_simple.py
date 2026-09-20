"""
In-memory rate limit: скользящее окно в переменных процесса, без Redis.

ENV: MVC_RATE_LIMIT_ENABLED=true (или enabled=True в декораторе)

Состояние: dict[identity, deque[timestamps]].
Для тестов время можно подменить через set_clock().
"""

from __future__ import annotations

import inspect
import time
from collections import deque
from typing import Any, Callable

from src.mybootstrap_mvc_fastapi_itskovichanton.infra._rate import (
    client_key,
    find_request,
    raise_exceeded,
)
from src.mybootstrap_mvc_fastapi_itskovichanton.infra._wrap import preserve_signature
from src.mybootstrap_mvc_fastapi_itskovichanton.infra.flags import flags

_clock: Callable[[], float] = time.monotonic
_hits: dict[str, deque[float]] = {}


def set_clock(clock: Callable[[], float] | None = None) -> None:
    global _clock
    _clock = clock or time.monotonic


def reset() -> None:
    _hits.clear()
    set_clock()


def _allow(identity: str, limit: int, window_sec: int) -> bool:
    now = _clock()
    cutoff = now - window_sec
    hits = _hits.setdefault(identity, deque())
    while hits and hits[0] <= cutoff:
        hits.popleft()
    if len(hits) >= limit:
        return False
    hits.append(now)
    return True


def _identity(
    bucket: str,
    key: str | Callable[..., Any] | None,
    fn: Callable,
    args: tuple,
    kwargs: dict,
) -> str:
    if key is None:
        return client_key(find_request(args, kwargs), bucket)
    if callable(key):
        return f"{bucket}:{key(*args, **kwargs)}"
    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs)
        bound.apply_defaults()
        if key in bound.arguments:
            return f"{bucket}:{bound.arguments[key]}"
    except (TypeError, ValueError):
        pass
    if key in kwargs:
        return f"{bucket}:{kwargs[key]}"
    return f"{bucket}:{key}"


def _guard(
    fn: Callable,
    args: tuple,
    kwargs: dict,
    bucket: str,
    limit: int | None,
    window_sec: int | None,
    key: str | Callable[..., Any] | None,
    enabled: bool | None,
) -> None:
    f = flags()
    on = f.rate_limit if enabled is None else enabled
    if not on:
        return
    lim = limit if limit is not None else f.rate_limit_default
    win = window_sec if window_sec is not None else f.rate_limit_window_sec
    if not _allow(_identity(bucket, key, fn, args, kwargs), lim, win):
        raise_exceeded(bucket, lim, win)


def _is_async(fn: Callable) -> bool:
    current: Any = fn
    while current is not None:
        if inspect.iscoroutinefunction(current):
            return True
        current = getattr(current, "__wrapped__", None)
    return False


def rate_limit(
    bucket: str,
    limit: int | None = None,
    window_sec: int | None = None,
    key: str | Callable[..., Any] | None = None,
    enabled: bool | None = None,
):
    """
    FastAPI:
        @rate_limit("avatar", limit=10, window_sec=60)
        async def upload_avatar(request: Request, ...): ...

    Обычная sync/async функция (ключ — имя аргумента):
        @rate_limit("sms", limit=3, window_sec=60, key="phone", enabled=True)
        async def send_sms(phone: str) -> None: ...
    """

    def decorator(fn: Callable):
        if _is_async(fn):
            async def async_wrapper(*args, **kwargs):
                _guard(fn, args, kwargs, bucket, limit, window_sec, key, enabled)
                return await fn(*args, **kwargs)

            return preserve_signature(async_wrapper, fn)

        def sync_wrapper(*args, **kwargs):
            _guard(fn, args, kwargs, bucket, limit, window_sec, key, enabled)
            return fn(*args, **kwargs)

        return preserve_signature(sync_wrapper, fn)

    return decorator
