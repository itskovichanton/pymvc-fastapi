"""
Simple rate-limiter на обычной функции — без FastAPI и без Request.

enabled=True — лимит работает сразу, ENV MVC_RATE_LIMIT_ENABLED не нужен.
key="phone" — отдельный счётчик на каждое значение аргумента phone.
Работает и на def, и на async def.
"""

from __future__ import annotations

import inspect

import pytest
from src.mybootstrap_mvc_itskovichanton.exceptions import (
    ERR_REASON_TOO_MANY_REQUESTS,
    CoreException,
)

from src.mybootstrap_mvc_fastapi_itskovichanton.infra.rate_limit_simple import (
    rate_limit,
    reset,
)


@pytest.fixture(autouse=True)
def _clean_limiter():
    reset()
    yield
    reset()


def test_plain_function_limited_per_argument():
    calls = []

    @rate_limit("send_code", limit=2, window_sec=60, key="phone", enabled=True)
    def send_code(phone: str) -> str:
        calls.append(phone)
        return f"sent:{phone}"

    assert send_code("+79990001122") == "sent:+79990001122"
    assert send_code("+79990001122") == "sent:+79990001122"
    with pytest.raises(CoreException) as err:
        send_code("+79990001122")
    assert err.value.reason == ERR_REASON_TOO_MANY_REQUESTS

    # другой ключ — свой лимит
    assert send_code("+71112223344") == "sent:+71112223344"
    assert calls == ["+79990001122", "+79990001122", "+71112223344"]


def test_plain_function_key_callable():
    @rate_limit(
        "notify",
        limit=1,
        window_sec=60,
        key=lambda user_id, text, channel="sms": f"{channel}:{user_id}",
        enabled=True,
    )
    def notify(user_id: int, text: str, channel: str = "sms") -> str:
        return f"{channel}:{user_id}:{text}"

    assert notify(7, "hi") == "sms:7:hi"
    with pytest.raises(CoreException):
        notify(7, "again")
    assert notify(7, "hi", channel="email") == "email:7:hi"


def test_plain_method_on_class():
    class OtpService:
        @rate_limit("otp", limit=1, window_sec=60, key="user_id", enabled=True)
        def send(self, user_id: str) -> str:
            return f"otp:{user_id}"

    svc = OtpService()
    assert svc.send("u1") == "otp:u1"
    with pytest.raises(CoreException):
        svc.send("u1")
    assert svc.send("u2") == "otp:u2"


@pytest.mark.asyncio
async def test_plain_async_function_limited_per_argument():
    calls = []

    @rate_limit("send_code", limit=2, window_sec=60, key="phone", enabled=True)
    async def send_code(phone: str) -> str:
        calls.append(phone)
        return f"sent:{phone}"

    assert inspect.iscoroutinefunction(send_code)
    assert await send_code("+79990001122") == "sent:+79990001122"
    assert await send_code("+79990001122") == "sent:+79990001122"
    with pytest.raises(CoreException) as err:
        await send_code("+79990001122")
    assert err.value.reason == ERR_REASON_TOO_MANY_REQUESTS
    assert await send_code("+71112223344") == "sent:+71112223344"
    assert calls == ["+79990001122", "+79990001122", "+71112223344"]


@pytest.mark.asyncio
async def test_plain_async_method_on_class():
    class OtpService:
        @rate_limit("otp", limit=1, window_sec=60, key="user_id", enabled=True)
        async def send(self, user_id: str) -> str:
            return f"otp:{user_id}"

    svc = OtpService()
    assert inspect.iscoroutinefunction(svc.send)
    assert await svc.send("u1") == "otp:u1"
    with pytest.raises(CoreException):
        await svc.send("u1")
    assert await svc.send("u2") == "otp:u2"
