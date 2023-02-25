import base64
import binascii

from fastapi import Request
from src.mybootstrap_mvc_itskovichanton.pipeline import Call
from starlette.authentication import AuthenticationError


def get_call_from_request(request: Request) -> Call:
    return Call(request=request, ip=get_ip(request), user_agent=request.headers.get("User-Agent"))


def get_ip(request: Request):
    h = request.client.host
    if h is None:
        return h
    for header in ("X-Forwarded-For", "X-Real-Ip"):
        h = request.headers.get(header)
        if h:
            return h
    return None


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
