"""
Rate limit через pyrate-limiter (Redis).

ENV: MVC_RATE_LIMIT_ENABLED=true
(fastapi-limiter 0.2 — только Depends; декоратор держим поверх pyrate_limiter.)
"""

from __future__ import annotations

from typing import Callable

import redis.asyncio as redis
from fastapi import Request
from pyrate_limiter import Duration, Limiter, Rate, RedisBucket
from src.mybootstrap_mvc_itskovichanton.exceptions import (
    ERR_REASON_TOO_MANY_REQUESTS,
    CoreException,
)

from infra._wrap import preserve_signature
from infra.flags import flags

# (limit, window_sec) → Limiter; один Redis-клиент на процесс
_limiters: dict[tuple[int, int], Limiter] = {}
_redis: redis.Redis | None = None


def _client_key(request: Request | None, bucket: str) -> str:
    ip = "anon"
    if request is not None:
        ip = request.client.host if request.client else "anon"
        tok = request.headers.get(flags().s2s_header)
        if tok:
            ip = f"svc:{tok[:8]}"
    return f"{bucket}:{ip}"


async def _redis_client() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(flags().redis_url, decode_responses=False)
    return _redis


async def _limiter_for(limit: int, window_sec: int) -> Limiter:
    key = (limit, window_sec)
    cached = _limiters.get(key)
    if cached is not None:
        return cached
    rates = [Rate(limit, Duration.SECOND * window_sec)]
    r = await _redis_client()
    bucket = await RedisBucket.init(rates, r, f"cityvibe:rl:{limit}:{window_sec}")
    lim = Limiter(bucket)
    _limiters[key] = lim
    return lim


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

            request: Request | None = kwargs.get("request")
            if request is None:
                for a in args:
                    if isinstance(a, Request):
                        request = a
                        break

            lim = limit if limit is not None else f.rate_limit_default
            win = window_sec if window_sec is not None else f.rate_limit_window_sec
            limiter = await _limiter_for(lim, win)
            ok = await limiter.try_acquire_async(_client_key(request, bucket), blocking=False)
            if not ok:
                raise CoreException(
                    message=f"Rate limit exceeded for '{bucket}' ({lim}/{win}s)",
                    reason=ERR_REASON_TOO_MANY_REQUESTS,
                )
            return await fn(*args, **kwargs)

        return preserve_signature(wrapper, fn)

    return decorator
