"""Feature-flags инфраструктуры из ENV. По умолчанию — удобно для local dev."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class InfraFlags:
    """Снимок флагов. Меняются только через ENV + рестарт процесса."""

    request_id: bool
    s2s_auth: bool
    s2s_token: str
    s2s_header: str
    s2s_skip_paths: tuple[str, ...]

    idempotency: bool
    idempotency_ttl_sec: int
    idempotency_header: str

    rate_limit: bool
    rate_limit_default: int
    rate_limit_window_sec: int

    upload_validation: bool
    upload_max_bytes: int
    upload_allowed_mime: tuple[str, ...]

    outbox: bool
    outbox_poll_sec: float

    tracing: bool
    otel_endpoint: str
    otel_service_name: str

    redis_url: str

    # Подробные HTTP-логи в файл loggers.http (тела запросов/ответов)
    http_log: bool
    http_log_max_body: int
    http_log_request_body: bool
    http_log_response_body: bool
    http_log_skip_paths: tuple[str, ...]


@lru_cache(maxsize=1)
def flags() -> InfraFlags:
    """Читает ENV один раз. Для тестов: flags.cache_clear()."""
    skip = env_str(
        "MVC_S2S_SKIP_PATHS",
        "/health,/docs,/redoc,/openapi.json",
    )
    mime = env_str(
        "MVC_UPLOAD_ALLOWED_MIME",
        "image/jpeg,image/png,image/webp,image/jpg",
    )
    http_skip = env_str(
        "MVC_HTTP_LOG_SKIP_PATHS",
        "/health,/docs,/redoc,/openapi.json,/favicon.ico",
    )
    return InfraFlags(
        # Request-ID почти бесплатный — по умолчанию ВКЛ
        request_id=env_bool("MVC_REQUEST_ID_ENABLED", True),
        # S2S / idempotency / rate-limit / outbox — по умолчанию ВЫКЛ (local-friendly)
        s2s_auth=env_bool("MVC_S2S_AUTH_ENABLED", False),
        s2s_token=env_str("MVC_S2S_TOKEN", "dev-s2s-token"),
        s2s_header=env_str("MVC_S2S_HEADER", "X-Service-Token"),
        s2s_skip_paths=tuple(p.strip() for p in skip.split(",") if p.strip()),
        idempotency=env_bool("MVC_IDEMPOTENCY_ENABLED", False),
        idempotency_ttl_sec=env_int("MVC_IDEMPOTENCY_TTL_SEC", 86400),
        idempotency_header=env_str("MVC_IDEMPOTENCY_HEADER", "Idempotency-Key"),
        rate_limit=env_bool("MVC_RATE_LIMIT_ENABLED", False),
        rate_limit_default=env_int("MVC_RATE_LIMIT_DEFAULT", 60),
        rate_limit_window_sec=env_int("MVC_RATE_LIMIT_WINDOW_SEC", 60),
        upload_validation=env_bool("MVC_UPLOAD_VALIDATION_ENABLED", True),
        upload_max_bytes=env_int("MVC_UPLOAD_MAX_BYTES", 5 * 1024 * 1024),
        upload_allowed_mime=tuple(m.strip().lower() for m in mime.split(",") if m.strip()),
        outbox=env_bool("MVC_OUTBOX_ENABLED", False),
        outbox_poll_sec=float(env_str("MVC_OUTBOX_POLL_SEC", "2")),
        # Tracing → Jaeger (нужен контейнер jaeger из infra-up)
        tracing=env_bool("MVC_TRACING_ENABLED", True),
        otel_endpoint=env_str("MVC_OTEL_ENDPOINT", "http://localhost:4317"),
        # Переопределять в make run-* / start-all (иначе все сервисы свалятся в одно имя)
        otel_service_name=env_str("MVC_OTEL_SERVICE_NAME", "city-vibe"),
        redis_url=env_str("MVC_REDIS_URL", "redis://localhost:6379/0"),
        # HTTP file logs — по умолчанию ON (подробные тела; для prod можно выключить)
        http_log=env_bool("MVC_HTTP_LOG_ENABLED", True),
        http_log_max_body=env_int("MVC_HTTP_LOG_MAX_BODY", 1_048_576),
        http_log_request_body=env_bool("MVC_HTTP_LOG_REQUEST_BODY", True),
        http_log_response_body=env_bool("MVC_HTTP_LOG_RESPONSE_BODY", True),
        http_log_skip_paths=tuple(p.strip() for p in http_skip.split(",") if p.strip()),
    )
