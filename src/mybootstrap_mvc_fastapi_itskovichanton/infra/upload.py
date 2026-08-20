"""
Валидация upload: размер + MIME через filetype (pure Python, без libmagic).

ENV: MVC_UPLOAD_VALIDATION_ENABLED=true (default on)
"""

from __future__ import annotations

from typing import Callable

import filetype
from fastapi import UploadFile
from src.mybootstrap_mvc_itskovichanton.exceptions import ERR_REASON_VALIDATION, CoreException

from infra.flags import flags

_EXT_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def sniff_mime(data: bytes) -> str | None:
    """Определяет MIME по содержимому (filetype)."""
    kind = filetype.guess(data)
    if kind is None:
        return None
    mime = (kind.mime or "").lower()
    if mime == "image/jpg":
        return "image/jpeg"
    return mime or None


async def read_validated_upload(file: UploadFile) -> tuple[bytes, str, str]:
    """
    Читает UploadFile с проверками. Возвращает (bytes, content_type, extension).
    No-op проверок, если MVC_UPLOAD_VALIDATION_ENABLED=false (кроме пустого файла).
    """
    data = await file.read()
    f = flags()
    if not data:
        raise CoreException(message="Пустой файл", reason=ERR_REASON_VALIDATION)

    declared = (file.content_type or "").split(";")[0].strip().lower() or "application/octet-stream"
    ext = (file.filename or "file.bin").rsplit(".", 1)[-1].lower()

    if not f.upload_validation:
        return data, declared, ext

    if len(data) > f.upload_max_bytes:
        raise CoreException(
            message=f"Файл слишком большой (max {f.upload_max_bytes} bytes)",
            reason=ERR_REASON_VALIDATION,
        )

    sniffed = sniff_mime(data)
    effective = sniffed or declared
    if effective == "image/jpg":
        effective = "image/jpeg"

    allowed = set(f.upload_allowed_mime) | {"image/jpg"}
    if effective not in allowed and declared not in allowed:
        raise CoreException(
            message=f"MIME '{effective}' не разрешён. Allowed: {sorted(f.upload_allowed_mime)}",
            reason=ERR_REASON_VALIDATION,
        )

    if sniffed:
        effective = sniffed
        ext = _EXT_BY_MIME.get(sniffed, ext)

    return data, effective, ext


def validate_upload(param: str = "file"):
    """Декоратор: кладёт результат в file.state.validated = (bytes, ctype, ext)."""

    def decorator(fn: Callable):
        async def wrapper(*args, **kwargs):
            upload: UploadFile | None = kwargs.get(param)
            if upload is None:
                return await fn(*args, **kwargs)
            data, ctype, ext = await read_validated_upload(upload)
            upload.state.validated = (data, ctype, ext)  # type: ignore[attr-defined]
            return await fn(*args, **kwargs)

        from infra._wrap import preserve_signature
        return preserve_signature(wrapper, fn)

    return decorator
