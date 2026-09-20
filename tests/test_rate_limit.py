"""Тесты in-memory и Redis rate-limiter."""

from __future__ import annotations

import asyncio
import inspect

import fakeredis.aioredis
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from src.mybootstrap_mvc_itskovichanton.exceptions import (
    ERR_REASON_TOO_MANY_REQUESTS,
    CoreException,
)

from src.mybootstrap_mvc_fastapi_itskovichanton.infra.flags import flags
from src.mybootstrap_mvc_fastapi_itskovichanton.infra import rate_limit as rl_redis
from src.mybootstrap_mvc_fastapi_itskovichanton.infra import rate_limit_simple as rl_simple


def make_request(ip: str = "127.0.0.1", headers: dict[str, str] | None = None) -> Request:
    header_list = []
    if headers:
        for key, value in headers.items():
            header_list.append((key.lower().encode(), value.encode()))
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": header_list,
            "client": (ip, 12345),
            "server": ("test", 80),
        }
    )


class Clock:
    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def rate_limit_on(monkeypatch):
    monkeypatch.setenv("MVC_RATE_LIMIT_ENABLED", "true")
    flags.cache_clear()
    yield
    flags.cache_clear()


@pytest.fixture
def simple(rate_limit_on):
    rl_simple.reset()
    yield rl_simple
    rl_simple.reset()


@pytest.fixture
async def redis_mod(rate_limit_on):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=False)
    rl_redis.configure_redis(fake)
    yield rl_redis
    rl_redis.reset()
    await fake.aclose()


async def _call(rate_limit, bucket: str, limit: int, window_sec: int, request: Request):
    @rate_limit(bucket, limit=limit, window_sec=window_sec)
    async def handler(request: Request):
        return "ok"

    return await handler(request=request)


async def _n_ok(rate_limit, n: int, request: Request, limit: int = 3, window_sec: int = 60):
    for _ in range(n):
        assert await _call(rate_limit, "t", limit, window_sec, request) == "ok"


# --- simple (in-memory) ---


@pytest.mark.asyncio
async def test_simple_allows_up_to_limit(simple):
    req = make_request()
    await _n_ok(simple.rate_limit, 3, req, limit=3)
    with pytest.raises(CoreException) as err:
        await _call(simple.rate_limit, "t", 3, 60, req)
    assert err.value.reason == ERR_REASON_TOO_MANY_REQUESTS
    assert "t" in err.value.message


@pytest.mark.asyncio
async def test_simple_isolates_clients(simple):
    await _n_ok(simple.rate_limit, 2, make_request("10.0.0.1"), limit=2)
    assert await _call(simple.rate_limit, "t", 2, 60, make_request("10.0.0.2")) == "ok"


@pytest.mark.asyncio
async def test_simple_isolates_buckets(simple):
    req = make_request()
    await _n_ok(simple.rate_limit, 1, req, limit=1)
    assert await _call(simple.rate_limit, "other", 1, 60, req) == "ok"


@pytest.mark.asyncio
async def test_simple_window_expires(simple):
    clock = Clock()
    simple.set_clock(clock)
    req = make_request()
    await _n_ok(simple.rate_limit, 2, req, limit=2, window_sec=10)
    with pytest.raises(CoreException):
        await _call(simple.rate_limit, "t", 2, 10, req)
    clock.advance(10.001)
    assert await _call(simple.rate_limit, "t", 2, 10, req) == "ok"


@pytest.mark.asyncio
async def test_simple_s2s_token_is_identity(simple):
    a = make_request("1.1.1.1", headers={"X-Service-Token": "abcdefghij"})
    b = make_request("9.9.9.9", headers={"X-Service-Token": "abcdefghij"})
    c = make_request("1.1.1.1", headers={"X-Service-Token": "zzzzzzzzzz"})
    await _n_ok(simple.rate_limit, 1, a, limit=1)
    with pytest.raises(CoreException):
        await _call(simple.rate_limit, "t", 1, 60, b)
    assert await _call(simple.rate_limit, "t", 1, 60, c) == "ok"


@pytest.mark.asyncio
async def test_simple_disabled_is_noop(monkeypatch, simple):
    monkeypatch.setenv("MVC_RATE_LIMIT_ENABLED", "false")
    flags.cache_clear()
    req = make_request()
    for _ in range(5):
        assert await _call(simple.rate_limit, "t", 1, 60, req) == "ok"


@pytest.mark.asyncio
async def test_simple_concurrent_does_not_overshoot(simple):
    req = make_request()

    @simple.rate_limit("c", limit=5, window_sec=60)
    async def ping(request: Request):
        return 1

    results = await asyncio.gather(
        *[ping(request=req) for _ in range(12)],
        return_exceptions=True,
    )
    oks = [r for r in results if r == 1]
    denied = [r for r in results if isinstance(r, CoreException)]
    assert len(oks) == 5
    assert len(denied) == 7


def test_simple_preserves_signature(simple):
    @simple.rate_limit("sig", limit=1, window_sec=1)
    async def handler(request: Request, q: str = "a"):
        return q

    params = inspect.signature(handler).parameters
    assert list(params) == ["request", "q"]


def test_simple_fastapi_route(simple):
    app = FastAPI()

    @app.get("/ping")
    @simple.rate_limit("ping", limit=2, window_sec=60)
    async def ping(request: Request):
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    # CoreException наследуется от BaseException — Starlette отдаёт 500
    assert client.get("/ping").status_code == 500


# --- redis ---


@pytest.mark.asyncio
async def test_redis_allows_up_to_limit(redis_mod):
    req = make_request()
    await _n_ok(redis_mod.rate_limit, 3, req, limit=3)
    with pytest.raises(CoreException) as err:
        await _call(redis_mod.rate_limit, "t", 3, 60, req)
    assert err.value.reason == ERR_REASON_TOO_MANY_REQUESTS


@pytest.mark.asyncio
async def test_redis_same_client_counts_each_request(redis_mod):
    """Регрессия: одинаковое имя item в Redis ZSET не должно затирать счётчик."""
    req = make_request("8.8.8.8")
    await _n_ok(redis_mod.rate_limit, 2, req, limit=2)
    with pytest.raises(CoreException):
        await _call(redis_mod.rate_limit, "t", 2, 60, req)


@pytest.mark.asyncio
async def test_redis_isolates_clients(redis_mod):
    await _n_ok(redis_mod.rate_limit, 2, make_request("10.0.0.1"), limit=2)
    assert await _call(redis_mod.rate_limit, "t", 2, 60, make_request("10.0.0.2")) == "ok"


@pytest.mark.asyncio
async def test_redis_window_expires(redis_mod):
    req = make_request()
    await _n_ok(redis_mod.rate_limit, 1, req, limit=1, window_sec=1)
    with pytest.raises(CoreException):
        await _call(redis_mod.rate_limit, "t", 1, 1, req)
    await asyncio.sleep(1.1)
    assert await _call(redis_mod.rate_limit, "t", 1, 1, req) == "ok"


@pytest.mark.asyncio
async def test_redis_concurrent_does_not_overshoot(redis_mod):
    req = make_request()

    @redis_mod.rate_limit("c", limit=5, window_sec=60)
    async def ping(request: Request):
        return 1

    results = await asyncio.gather(
        *[ping(request=req) for _ in range(12)],
        return_exceptions=True,
    )
    oks = [r for r in results if r == 1]
    denied = [r for r in results if isinstance(r, CoreException)]
    assert len(oks) == 5
    assert len(denied) == 7


@pytest.mark.asyncio
async def test_redis_preserves_signature(redis_mod):
    @redis_mod.rate_limit("sig", limit=1, window_sec=1)
    async def handler(request: Request, q: str = "a"):
        return q

    assert list(inspect.signature(handler).parameters) == ["request", "q"]
