import json
import time
from typing import Any, Dict, Optional, Union, Callable
from datetime import datetime, timezone
import re
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import logging


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
            excluded_paths: Optional[set] = None
    ):
        super().__init__(app)
        self.logger = logger
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
        client_ip = self._get_client_ip(request)
        client_port = request.client.port if request.client else None

        # Читаем тело запроса (если нужно)
        request_body = await self._read_request_body(request) if self.log_request_body else None

        # Засекаем время выполнения
        start_time = time.perf_counter()

        # Выполняем запрос
        response = await call_next(request)

        # Вычисляем время выполнения
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Читаем тело ответа (если нужно)
        response_body = await self._read_response_body(response) if self.log_response_body else None

        # Формируем и логируем структурированный JSON
        self._log_request_response(
            request=request,
            response=response,
            client_ip=client_ip,
            client_port=client_port,
            request_body=request_body,
            response_body=response_body,
            elapsed_ms=elapsed_ms
        )

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Получение реального IP клиента с учетом прокси"""
        if "x-real-ip" in request.headers:
            return request.headers["x-real-ip"]
        elif "x-forwarded-for" in request.headers:
            # Берем первый IP из цепочки
            return request.headers["x-forwarded-for"].split(',')[0].strip()
        elif request.client:
            return request.client.host
        return "unknown"

    async def _read_request_body(self, request: Request) -> Optional[Union[str, bytes]]:
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
                    if self._is_likely_text(text_body):
                        return self._sanitize_and_truncate(text_body)
                except (UnicodeDecodeError, UnicodeEncodeError):
                    pass

                # Если не удалось декодить как текст, возвращаем информацию о размере
                return f"bytes[{len(body)}]"

            return body

        except Exception as e:
            self.logger.debug(f"Failed to read request body: {e}")
            return f"error_reading_body: {str(e)}"

    async def _read_response_body(self, response: Response) -> Optional[Union[str, bytes]]:
        """Чтение тела ответа"""
        try:
            # Клонируем ответ для чтения тела
            body = b""
            async for chunk in response.body_iterator:
                body += chunk

            # Восстанавливаем итератор
            response.body_iterator = self._recreate_body_iterator(body)

            # Если тело пустое
            if not body:
                return None

            # Пробуем декодить как текст
            content_type = response.headers.get('content-type', '').lower()
            if 'application/json' in content_type or 'text/' in content_type:
                try:
                    text_body = body.decode('utf-8')
                    return self._sanitize_and_truncate(text_body)
                except (UnicodeDecodeError, UnicodeEncodeError):
                    pass

            # Для бинарных данных возвращаем информацию о размере
            return f"bytes[{len(body)}]"

        except Exception as e:
            self.logger.debug(f"Failed to read response body: {e}")
            return f"error_reading_body: {str(e)}"

    @staticmethod
    async def _recreate_body_iterator(body: bytes):
        """Воссоздание итератора тела"""
        yield body

    def _sanitize_and_truncate(self, text: str) -> str:
        """Очистка чувствительных данных и усечение строки"""
        # Сначала усекаем
        if len(text) > self.max_field_len:
            text = text[:self.max_field_len] + "...[truncated]"

        # Затем маскируем чувствительные данные
        return self._mask_sensitive_data(text)

    def _mask_sensitive_data(self, text: str) -> str:
        """Маскировка чувствительных данных в тексте"""
        # Простая маскировка паролей в JSON
        for pattern in self._sensitive_patterns:
            if pattern.search(text):
                # Ищем и маскируем значения чувствительных полей
                text = re.sub(
                    r'("' + pattern.pattern + r'"\s*:\s*)"([^"]*)"',
                    r'\1"***MASKED***"',
                    text,
                    flags=re.IGNORECASE
                )
        return text

    def _is_likely_text(self, text: str) -> bool:
        """Проверяет, похож ли контент на текст"""
        # Если много непечатаемых символов - вероятно бинарные данные
        if len(text) == 0:
            return True

        non_printable = sum(1 for c in text if ord(c) < 32 and c not in '\n\r\t')
        ratio = non_printable / len(text)
        return ratio < 0.1  # Если меньше 10% непечатаемых символов

    def _sanitize_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Очистка заголовков от чувствительных данных"""
        sanitized = {}
        for key, value in headers.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in self.sensitive_fields):
                sanitized[key] = "***MASKED***"
            else:
                sanitized[key] = value
        return sanitized

    def _parse_query_params(self, request: Request) -> Dict[str, Any]:
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

    def _log_request_response(
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
                "request_headers": self._sanitize_headers(dict(request.headers)),
                "params": self._parse_query_params(request),
                "request-body": request_body,
                "from": {
                    "ip": client_ip,
                    "port": client_port
                }
            },
            "method": request.method,
            "url": str(request.url),
            "response": {
                "response_headers": self._sanitize_headers(dict(response.headers)),
                "body": response_body,
                "response_code": response.status_code,
                "elapsed_ms": round(elapsed_ms, 2)
            }
        }

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
