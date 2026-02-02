import base64
import binascii
import json
import re
from dataclasses import is_dataclass, dataclass
from typing import Optional, Union, Dict, Any

import requests
from dacite import from_dict, Config
from fastapi import Request
from pydantic import BaseModel, Extra
from src.mybootstrap_core_itskovichanton.utils import is_listable
from src.mybootstrap_core_itskovichanton.validation import ValidationException
from src.mybootstrap_mvc_itskovichanton.exceptions import CoreException, ERR_REASON_VALIDATION, \
    ERR_REASON_SERVER_RESPONDED_WITH_ERROR, ERR_REASON_INTERNAL, ERR_REASON_SERVER_RESPONDED_WITH_ERROR_NOT_FOUND
from src.mybootstrap_mvc_itskovichanton.pipeline import Call
from starlette.authentication import AuthenticationError
from starlette.responses import Response


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


def parse_response(r: dict | requests.models.Response | str, reason_mapping: dict[str, str] = None, cl=None):
    if type(r) == str:
        r = json.loads(r)
    http_code = 0
    if isinstance(r, requests.models.Response):
        http_code = r.status_code
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
        raise CoreException(message=detail,
                            reason=ERR_REASON_SERVER_RESPONDED_WITH_ERROR_NOT_FOUND
                            if http_code == 404 else ERR_REASON_INTERNAL)
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

    r = r.get("result")
    if cl:
        if is_listable(r):
            @dataclass
            class _Wrapped:
                value: cl

            r = from_dict(data_class=_Wrapped, data={"value": r}, config=Config(check_types=False)).value
        else:
            r = from_dict(data_class=cl, data=r, config=Config(check_types=False))
    return r


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
            return source
            # raise TypeError('Source should be a dataclass')
        r = _M()
        for k, v in source.__dict__.items():
            setattr(r, k, to_pydantic_model(v))
        return r

    return source


def get_middleware_instances(app):
    instances = []
    current = app.middleware_stack

    while hasattr(current, "app"):
        instances.append(current)
        current = current.app

    return instances


async def _recreate_body_iterator(body: bytes):
    """Воссоздание итератора тела"""
    yield body


def _sanitize_and_truncate(text: str, sensitive_patterns=[], max_field_len: int = 1000) -> str:
    """Очистка чувствительных данных и усечение строки"""
    # Сначала усекаем
    if len(text) > max_field_len:
        text = text[:max_field_len] + "...[truncated]"

    # Затем маскируем чувствительные данные
    return _mask_sensitive_data(text, sensitive_patterns)


def _mask_sensitive_data(text: str, _sensitive_patterns) -> str:
    """Маскировка чувствительных данных в тексте"""
    # Простая маскировка паролей в JSON
    for pattern in _sensitive_patterns:
        if pattern.search(text):
            # Ищем и маскируем значения чувствительных полей
            text = re.sub(
                r'("' + pattern.pattern + r'"\s*:\s*)"([^"]*)"',
                r'\1"***MASKED***"',
                text,
                flags=re.IGNORECASE
            )
    return text


async def _read_response_body(response: Response, max_len=-1) -> Optional[Union[str, bytes]]:
    """Чтение тела ответа"""
    try:

        # Клонируем ответ для чтения тела
        body = b""
        async for chunk in response.body_iterator:
            if max_len > 0 and len(body) >= max_len:
                break
            body += chunk

        # Восстанавливаем итератор
        response.body_iterator = _recreate_body_iterator(body)

        # Если тело пустое
        if not body:
            return None

        # Пробуем декодить как текст
        content_type = response.headers.get('content-type', '').lower()
        if 'application/json' in content_type or 'text/' in content_type:
            try:
                text_body = body.decode('utf-8')
                max_field_len = 3000 if 500 <= response.status_code < 600 else 1500
                return _sanitize_and_truncate(text_body, max_field_len=max_field_len)
            except (UnicodeDecodeError, UnicodeEncodeError):
                pass

        # Для бинарных данных возвращаем информацию о размере
        return f"bytes[{len(body)}]"

    except Exception as e:
        return f"error_reading_body: {str(e)}"


async def _read_request_body(request: Request, _sensitive_patterns, max_field_len) -> Optional[Union[str, bytes]]:
    """Асинхронное чтение тела запроса с кэшированием"""
    try:
        # Проверяем, есть ли тело
        if request.method not in ("POST", "PUT", "PATCH"):
            return None

        # Читаем тело
        body = await request.body()

        # Если это байты и не текст, возвращаем информацию о размере
        if isinstance(body, bytes):
            # Пробуем декодить как текст
            try:
                text_body = body.decode('utf-8')
                # Проверяем, не содержит ли тело бинарные данные
                if _is_likely_text(text_body):
                    return _sanitize_and_truncate(text_body, _sensitive_patterns, max_field_len)
            except (UnicodeDecodeError, UnicodeEncodeError):
                pass

            # Если не удалось декодить как текст, возвращаем информацию о размере
            return f"bytes[{len(body)}]"

        return body

    except Exception as e:
        return f"error_reading_body: {str(e)}"


def _is_likely_text(text: str) -> bool:
    """Проверяет, похож ли контент на текст"""
    # Если много непечатаемых символов - вероятно бинарные данные
    if len(text) == 0:
        return True

    non_printable = sum(1 for c in text if ord(c) < 32 and c not in '\n\r\t')
    ratio = non_printable / len(text)
    return ratio < 0.1  # Если меньше 10% непечатаемых символов


def _sanitize_headers(headers: Dict[str, str], sensitive_fields) -> Dict[str, str]:
    """Очистка заголовков от чувствительных данных"""
    sanitized = {}
    for key, value in headers.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in sensitive_fields):
            sanitized[key] = "***MASKED***"
        else:
            sanitized[key] = value
    return sanitized


def _parse_query_params(request: Request) -> Dict[str, Any]:
    """Парсинг query параметров"""
    params = {}
    for key, value in request.query_params.multi_items():
        # Для многозначных параметров собираем список
        if key in params:
            if isinstance(params[key], list):
                params[key].append(value)
            else:
                params[key] = [params[key], value]
        else:
            params[key] = value
    return params


def _get_client_ip(request: Request) -> str:
    """Получение реального IP клиента с учетом прокси"""
    if "x-real-ip" in request.headers:
        return request.headers["x-real-ip"]
    elif "x-forwarded-for" in request.headers:
        # Берем первый IP из цепочки
        return request.headers["x-forwarded-for"].split(',')[0].strip()
    elif request.client:
        return request.client.host
    return "unknown"
