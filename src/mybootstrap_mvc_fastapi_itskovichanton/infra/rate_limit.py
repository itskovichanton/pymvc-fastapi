"""
Rate limit через pyrate-limiter (Redis).

ENV: MVC_RATE_LIMIT_ENABLED=true

Каждый клиент (IP / S2S-токен) получает свой Redis ZSET.
Имя элемента в ZSET уникально на каждый запрос: иначе ZADD обновляет
одну и ту же запись и лимит никогда не срабатывает.
"""

from __future__ import annotations

import inspect
import time
from typing import Callable

import redis.asyncio as redis
from pyrate_limiter import Duration, Limiter, Rate, RedisBucket
from pyrate_limiter.exceptions import BucketFullException

from src.mybootstrap_mvc_fastapi_itskovichanton.infra._rate import (
    client_key,
    find_request,
    raise_exceeded,
)
from src.mybootstrap_mvc_fastapi_itskovichanton.infra._wrap import preserve_signature
from src.mybootstrap_mvc_fastapi_itskovichanton.infra.flags import flags

# (limit, window_sec, identity) → Limiter
_limiters: dict[tuple[int, int, str], Limiter] = {}
_redis: redis.Redis | None = None


def configure_redis(client: redis.Redis | None) -> None:
    """Подменить Redis-клиент (для тестов: fakeredis). Сбрасывает кэш лимитеров."""
    global _redis
    _redis = client
    _limiters.clear()


def reset() -> None:
    configure_redis(None)


async def _redis_client() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(flags().redis_url, decode_responses=False)
    return _redis


async def _limiter_for(limit: int, window_sec: int, identity: str) -> Limiter:
    cache_key = (limit, window_sec, identity)
    cached = _limiters.get(cache_key)
    if cached is not None:
        return cached

    rates = [Rate(limit, Duration.SECOND * window_sec)]
    r = await _redis_client()
    bucket_key = f"mvc:rl:{limit}:{window_sec}:{identity}"
    bucket = RedisBucket.init(rates, r, bucket_key)
    if inspect.isawaitable(bucket):
        bucket = await bucket

    limiter = Limiter(bucket, raise_when_fail=False)
    _limiters[cache_key] = limiter
    return limiter


async def _try_acquire(limiter: Limiter, identity: str) -> bool:
    # ZSET-member должен быть уникален на каждый acquire (см. модульный docstring).
    item = f"{identity}:{time.time_ns()}"
    try:
        return bool(await limiter.try_acquire_async(item))
    except BucketFullException:
        return False


def rate_limit(bucket: str, limit: int | None = None, window_sec: int | None = None):
    """
        @app.post("/users/{id}/avatar")
        @rate_limit("avatar", limit=10, window_sec=60)
        async def upload_avatar(request: Request, ...):
    """

    def decorator(fn: Callable):
        async def wrapper(*args, **kwargs):
            f = flags()
            if not f.rate_limit:
                return await fn(*args, **kwargs)

            request = find_request(args, kwargs)
            lim = limit if limit is not None else f.rate_limit_default
            win = window_sec if window_sec is not None else f.rate_limit_window_sec
            identity = client_key(request, bucket)
            limiter = await _limiter_for(lim, win, identity)
            if not await _try_acquire(limiter, identity):
                raise_exceeded(bucket, lim, win)
            return await fn(*args, **kwargs)

        return preserve_signature(wrapper, fn)

    return decorator
