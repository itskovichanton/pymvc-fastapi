"""Общие хелперы для rate-limit декораторов."""

from __future__ import annotations

from fastapi import Request
from src.mybootstrap_mvc_itskovichanton.exceptions import (
    ERR_REASON_TOO_MANY_REQUESTS,
    CoreException,
)

from src.mybootstrap_mvc_fastapi_itskovichanton.infra.flags import flags


def find_request(args: tuple, kwargs: dict) -> Request | None:
    request = kwargs.get("request")
    if isinstance(request, Request):
        return request
    for arg in args:
        if isinstance(arg, Request):
            return arg
    return None


def client_key(request: Request | None, bucket: str) -> str:
    ip = "anon"
    if request is not None:
        ip = request.client.host if request.client else "anon"
        tok = request.headers.get(flags().s2s_header)
        if tok:
            ip = f"svc:{tok[:8]}"
    return f"{bucket}:{ip}"


def raise_exceeded(bucket: str, limit: int, window_sec: int) -> None:
    raise CoreException(
        message=f"Rate limit exceeded for '{bucket}' ({limit}/{window_sec}s)",
        reason=ERR_REASON_TOO_MANY_REQUESTS,
    )
