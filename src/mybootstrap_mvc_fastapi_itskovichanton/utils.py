from fastapi import Request
from src.mybootstrap_mvc_itskovichanton.pipeline import Call


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
