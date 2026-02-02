import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional, Union, Callable

from fastapi import Request, Response
from src.mybootstrap_mvc_fastapi_itskovichanton.utils import _read_response_body, _sanitize_headers, \
    _parse_query_params, _read_request_body, _get_client_ip
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class HTTPLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware для логирования HTTP запросов и ответов в структурированном JSON формате"""

    def __init__(
            self,
            app: ASGIApp,
            logger: logging.Logger,
            encoding: str = "utf-8",
            max_field_len: int = 5000,
            log_request_body: bool = True,
            log_response_body: bool = True,
            sensitive_fields: Optional[set] = None,
            excluded_paths: Optional[set] = None,
            on_request=None
    ):
        super().__init__(app)
        self.logger = logger
        self.on_request = on_request
        self.max_field_len = max_field_len
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.sensitive_fields = sensitive_fields or {
            # 'password', 'token', 'secret', 'authorization',
            # 'apikey', 'api_key', 'access_token', 'refresh_token'
        }
        self.excluded_paths = excluded_paths or {'/healthcheck',
                                                 # '/health', '/metrics', '/docs', '/openapi.json'
                                                 }

        # Компилируем паттерны для быстрой проверки
        self._sensitive_patterns = [
            re.compile(rf'\b{field}\b', re.IGNORECASE)
            for field in self.sensitive_fields
        ]

    async def dispatch(self, request: Request, call_next: Callable):
        # Пропускаем excluded пути
        path = request.url.path
        if path in self.excluded_paths:
            return await call_next(request)

        # Получаем IP и порт клиента
        client_ip = _get_client_ip(request)
        client_port = request.client.port if request.client else None

        # Читаем тело запроса (если нужно)
        request_body = await _read_request_body(request, self.sensitive_fields,
                                                self.max_field_len) if self.log_request_body else None

        # Засекаем время выполнения
        start_time = time.perf_counter()

        # Выполняем запрос
        response = await call_next(request)

        # Вычисляем время выполнения
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Читаем тело ответа (если нужно)
        response_body = await _read_response_body(response) if self.log_response_body else None

        # Формируем и логируем структурированный JSON
        await self._log_request_response(
            request=request,
            response=response,
            client_ip=client_ip,
            client_port=client_port,
            request_body=request_body,
            response_body=response_body,
            elapsed_ms=elapsed_ms
        )

        return response

    async def _log_request_response(
            self,
            request: Request,
            response: Response,
            client_ip: str,
            client_port: Optional[int],
            request_body: Optional[Union[str, bytes]],
            response_body: Optional[Union[str, bytes]],
            elapsed_ms: float
    ):
        """Формирование и логирование структурированного JSON"""
        log_data = {
            "t": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            "request": {
                "request_headers": _sanitize_headers(dict(request.headers), self.sensitive_fields),
                "params": _parse_query_params(request),
                "request-body": request_body,
                "from": {
                    "ip": client_ip,
                    "port": client_port
                }
            },
            "method": request.method,
            "url": str(request.url),
            "response": {
                "response_headers": _sanitize_headers(dict(response.headers), self.sensitive_fields),
                "body": response_body,
                "response_code": response.status_code,
                "elapsed_ms": round(elapsed_ms, 2)
            }
        }

        if self.on_request:
            await self.on_request(log_data)

        self.logger.info(log_data)

    @classmethod
    def configure(
            cls,
            logger_name: str = "http",
            max_field_len: int = 5000,
            log_request_body: bool = True,
            log_response_body: bool = True,
            sensitive_fields: Optional[set] = None,
            excluded_paths: Optional[set] = None
    ):
        """Фабричный метод для удобной конфигурации"""

        # Создаем логгер
        logger = logging.getLogger(logger_name)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(message)s')  # Только сообщение, т.к. логируем JSON
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False

        def _middleware_factory(app: ASGIApp):
            return cls(
                app=app,
                logger=logger,
                max_field_len=max_field_len,
                log_request_body=log_request_body,
                log_response_body=log_response_body,
                sensitive_fields=sensitive_fields,
                excluded_paths=excluded_paths
            )

        return _middleware_factory
