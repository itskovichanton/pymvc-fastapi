import base64
import binascii
from dataclasses import is_dataclass, asdict
from inspect import isclass

import requests
from fastapi import Request
from pydantic import BaseModel, Extra
from src.mybootstrap_core_itskovichanton.validation import ValidationException
from src.mybootstrap_mvc_itskovichanton.exceptions import CoreException, ERR_REASON_VALIDATION, \
    ERR_REASON_SERVER_RESPONDED_WITH_ERROR, ERR_REASON_INTERNAL
from src.mybootstrap_mvc_itskovichanton.pipeline import Call
from starlette.authentication import AuthenticationError


def get_call_from_request(request: Request) -> Call:
    return Call(request=request, ip=get_ip(request), user_agent=request.headers.get("User-Agent"))


def get_ip(request: Request):
    for header in ("X-Forwarded-For", "X-Real-Ip"):
        h = request.headers.get(header)
        if h:
            return h
    return request.client.host


def object_to_dict(obj):
    data = {}
    if getattr(obj, '__dict__', None):
        for key, value in obj.__dict__.items():
            try:
                data[key] = object_to_dict(value)
            except AttributeError:
                data[key] = value
        return data
    else:
        return obj


def tuple_to_dict(t: list):
    return dict((x, y) for x, y in t)


def get_basic_auth(conn) -> (str, str):
    if "Authorization" not in conn.headers:
        return

    auth = conn.headers["Authorization"]
    try:
        scheme, credentials = auth.split()
        if scheme.lower() != 'basic':
            return
        decoded = base64.b64decode(credentials).decode("ascii")
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise AuthenticationError('Invalid basic auth credentials')

    username, _, password = decoded.partition(":")
    return username, password


def parse_response(r: dict | requests.models.Response, reason_mapping: dict[str, str] = None):
    if isinstance(r, requests.models.Response):
        try:
            r = r.json()
        except:
            msg = r.text
            if 200 <= r.status_code <= 300:
                r = {"result": msg}
            else:
                r = {"error": {"message": msg}}

    detail = r.get("detail")
    if detail:
        raise CoreException(message=detail, reason=ERR_REASON_INTERNAL)
    error = r.get("error")
    if error:
        reason = error.get("reason")
        if reason_mapping is not None:
            reason = reason_mapping.get(reason) or ERR_REASON_SERVER_RESPONDED_WITH_ERROR
            error["reason"] = reason
        if reason == ERR_REASON_VALIDATION:
            raise ValidationException(validation_reason=error.get("cause"), message=error.get("message"),
                                      param=error.get("param"), invalid_value=error.get("invalidValue"))
        raise CoreException(**error)
    return r.get("result")


async def get_params_from_request(request: Request) -> dict:
    params = dict(request.query_params)
    if request.method == "POST":
        try:
            f = await request.form()
            params.update(f.items())
        except:
            ...
    return params


class _M(BaseModel):
    class Config:
        extra = Extra.allow


def to_pydantic_model(source) -> BaseModel:
    if source.__class__.__module__ != 'builtins':
        if not is_dataclass(source):
            raise TypeError('Source should be a dataclass')
        r = _M()
        for k, v in source.__dict__.items():
            setattr(r, k, to_pydantic_model(v))
        return r

    return source
