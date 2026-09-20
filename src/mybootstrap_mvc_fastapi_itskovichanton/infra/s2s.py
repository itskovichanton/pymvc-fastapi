"""
S2S auth: общий секрет в заголовке (без TLS/mTLS).

ENV:
  MVC_S2S_AUTH_ENABLED=true
  MVC_S2S_TOKEN=...
  MVC_S2S_HEADER=X-Service-Token
"""

from __future__ import annotations

import hmac
from typing import Callable

from fastapi import Request
from src.mybootstrap_mvc_itskovichanton.exceptions import (
    ERR_REASON_ACCESS_DENIED,
    ERR_REASON_AUTH_REQUIRED,
    CoreException,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from infra._wrap import preserve_signature
from infra.flags import flags


def _extract_token(request: Request) -> str | None:
    f = flags()
    direct = request.headers.get(f.s2s_header)
    if direct:
        return direct
    # совместимость с on_mbclient_api (auth.session_token → sessionToken)
    st = request.headers.get("sessionToken")
    if st:
        return st
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def verify_s2s_token(token: str | None) -> None:
    """Проверка токена. No-op если MVC_S2S_AUTH_ENABLED=false."""
    f = flags()
    if not f.s2s_auth:
        return
    if not token:
        raise CoreException(message="Требуется S2S-токен сервиса", reason=ERR_REASON_AUTH_REQUIRED)
    if not hmac.compare_digest(token, f.s2s_token):
        raise CoreException(message="Неверный S2S-токен", reason=ERR_REASON_ACCESS_DENIED)


def require_s2s(func: Callable | None = None):
    """
    Декоратор эндпоинта: требует валидный S2S-токен (если флаг включён).

        @app.post("/users")
        @require_s2s
        async def create_user(request: Request, ...):
            ...
    """

    def decorator(fn: Callable):
        async def wrapper(*args, **kwargs):
            request: Request | None = kwargs.get("request")
            if request is None:
                for a in args:
                    if isinstance(a, Request):
                        request = a
                        break
            if request is not None:
                verify_s2s_token(_extract_token(request))
            else:
                if flags().s2s_auth:
                    raise CoreException(
                        message="@require_s2s: добавьте request: Request в сигнатуру хендлера",
                        reason=ERR_REASON_ACCESS_DENIED,
                    )
            return await fn(*args, **kwargs)

        return preserve_signature(wrapper, fn)

    if func is not None:
        return decorator(func)
    return decorator


class S2SAuthMiddleware(BaseHTTPMiddleware):
    """Глобальная проверка S2S на всех путях, кроме skip-list (health/docs)."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        f = flags()
        if not f.s2s_auth:
            return await call_next(request)

        path = request.url.path
        if path in f.s2s_skip_paths or any(
                path.startswith(p.rstrip("/") + "/") for p in f.s2s_skip_paths if p.endswith("/*")):
            return await call_next(request)
        # точное и prefix-совпадение для /docs
        if any(path == p or path.startswith(p + "/") for p in f.s2s_skip_paths):
            return await call_next(request)

        try:
            verify_s2s_token(_extract_token(request))
        except CoreException as e:
            return JSONResponse(
                status_code=401 if e.reason == ERR_REASON_AUTH_REQUIRED else 403,
                content={"error": {"message": e.message, "reason": e.reason}},
            )
        return await call_next(request)
