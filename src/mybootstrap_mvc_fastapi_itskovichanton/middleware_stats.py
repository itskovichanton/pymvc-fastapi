from dataclasses import dataclass, asdict, field
from typing import List, Optional, Tuple, Deque, Dict, Any
from collections import deque, defaultdict
import time
from datetime import datetime, timedelta
from fastapi import Request, Response
from src.mybootstrap_core_itskovichanton.utils import hashed, to_dict_deep
from src.mybootstrap_ioc_itskovichanton.ioc import bean
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import statistics
from functools import lru_cache


@dataclass
class UrlStatsRecord:
    url: str
    time: str


@dataclass
class UrlStats:
    count: int = 0
    response: str = None
    last_urls: Deque[UrlStatsRecord] = field(default_factory=lambda: deque(maxlen=10))

    def inc(self, url, response_body=None):
        self.count += 1
        self.last_urls.append(UrlStatsRecord(url=str(url), response=response_body, time=str(datetime.now())))

    def summary(self) -> dict:
        return {"count": self.count, "last_urls": list(self.last_urls)}


@bean
class StatsHolder:

    def init(self, **kwargs):
        self._stats = {}
        self._statuses = defaultdict(UrlStats)

    def update(self, stats):
        self._stats = stats

    def get(self):
        return to_dict_deep({"time": self._stats,
                             "responses": {k: v.summary() for k, v in self._statuses.items()}})


@hashed
@dataclass
class RequestRecord:
    """Запись о выполненном запросе"""
    url: str
    method: str
    elapsed_ms: float
    content_type: Optional[str] = None
    content_length: Optional[int] = None
    status_code: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __lt__(self, other: 'RequestRecord') -> bool:
        """Для сравнения по времени выполнения (для сортировки)"""
        return self.elapsed_ms < other.elapsed_ms

    def __gt__(self, other: 'RequestRecord') -> bool:
        return self.elapsed_ms > other.elapsed_ms


@dataclass
class LongRequest:
    """Долгий запрос для вывода в статистике"""
    url: str
    elapsed_ms: float
    content_type: Optional[str] = None
    content_length: Optional[int] = None
    method: str = ""
    status_code: int = 0


@dataclass
class RequestStats:
    """Общая статистика по запросам"""
    avg_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0
    min_response_time_ms: float = 0.0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    requests_per_second: float = 0.0


@dataclass
class AggregatedStats:
    """Агрегированная статистика для отдачи клиенту"""
    avg_response_time: float
    max_response_time: float
    min_response_time: float
    total_requests: int
    most_long_requests: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StatisticsMiddleware(BaseHTTPMiddleware):
    """Middleware для сбора статистики по HTTP запросам"""

    def __init__(
            self,
            app: ASGIApp,
            max_records: int = 500,
            excluded_paths: Optional[set] = None,
            stats_holder: StatsHolder = None,
    ):
        super().__init__(app)
        self.max_records = max_records
        self.stats_holder = stats_holder
        self._last_stats_set_time = None

        # Используем deque для ограниченного хранения записей
        self._records: Deque[RequestRecord] = deque(maxlen=max_records)
        self._lock = None  # В async context будем использовать asyncio.Lock

        # Кэш для статистики
        self._stats_cache: Optional[AggregatedStats] = None
        self._cache_timestamp: float = 0
        self._cache_ttl: float = 1.0  # Кэшируем на 1 секунду

        # Исключенные пути
        self.excluded_paths = excluded_paths or {
            '/healthcheck', '/metrics', '/stats',
            '/docs', '/redoc', '/openapi.json'
        }

        # Вспомогательные счетчики
        self._total_counter: int = 0
        self._success_counter: int = 0
        self._start_time: float = time.time()

    async def dispatch(self, request: Request, call_next):
        # Пропускаем исключенные пути
        path = request.url.path
        if path in self.excluded_paths:
            return await call_next(request)

        # Засекаем время
        start_time = time.perf_counter()

        # Выполняем запрос
        response = await call_next(request)

        # Вычисляем время выполнения
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Собираем информацию о запросе
        await self._record_request(request, response, elapsed_ms)

        # Инвалидируем кэш статистики
        self._invalidate_cache()

        return response

    async def _record_request(self, request: Request, response: Response, elapsed_ms: float):
        """Запись информации о выполненном запросе"""

        # Получаем заголовки
        content_type = response.headers.get('content-type')
        content_length = response.headers.get('content-length')

        # Конвертируем content_length в int если возможно
        try:
            content_length_int = int(content_length) if content_length else None
        except (ValueError, TypeError):
            content_length_int = None

        # Создаем запись
        record = RequestRecord(
            url=str(request.url),
            method=request.method,
            elapsed_ms=elapsed_ms,
            content_type=content_type,
            content_length=content_length_int,
            status_code=response.status_code,
            timestamp=datetime.utcnow()
        )

        # Добавляем в очередь (автоматически ограничивается maxlen)
        self._records.append(record)

        # Обновляем счетчики
        self._total_counter += 1
        if 200 <= response.status_code < 300:
            self._success_counter += 1

        if 500 <= response.status_code <= 600:
            # response_body = await _read_response_body(response, max_len=200)
            response_body = None
            self.stats_holder._statuses[str(response.status_code)].inc(request.url, response_body)

        if (self._total_counter % 50 == 0 or (not self.stats_holder._stats) or
                (self._last_stats_set_time and datetime.now() - self._last_stats_set_time > timedelta(seconds=10))):
            self._last_stats_set_time = datetime.now()
            self.stats_holder.update(self.get_extended_stats())

    def _invalidate_cache(self):
        """Инвалидация кэша статистики"""
        self._stats_cache = None

    def _get_records_snapshot(self) -> Tuple[RequestRecord, ...]:
        """Получение неизменяемого снимка записей"""
        # Создаем tuple для гарантии неизменяемости
        return tuple(self._records)

    @lru_cache(maxsize=1)
    def _calculate_stats(self, records_hash: int) -> AggregatedStats:
        """Вычисление статистики (с кэшированием)"""
        records = self._get_records_snapshot()

        if not records:
            return AggregatedStats(
                avg_response_time=0.0,
                max_response_time=0.0,
                min_response_time=0.0,
                total_requests=0,
                most_long_requests=[]
            )

        # Сортируем по времени выполнения (самые долгие первыми)
        sorted_records = sorted(records, key=lambda r: r.elapsed_ms, reverse=True)

        # Берем топ-5 самых долгих запросов
        top_records = sorted_records[:5]

        # Подготавливаем список долгих запросов
        long_requests = []
        for record in top_records:
            long_requests.append({
                "url": record.url,
                "elapsed": round(record.elapsed_ms, 2),
                "content_type": record.content_type,
                "content_length": record.content_length,
                "method": record.method,
                "status_code": record.status_code
            })

        # Вычисляем статистику
        times = [r.elapsed_ms for r in records]

        return AggregatedStats(
            avg_response_time=round(statistics.mean(times), 2),
            max_response_time=round(max(times), 2),
            min_response_time=round(min(times), 2),
            total_requests=len(records),
            most_long_requests=long_requests
        )

    def get_stats(self) -> AggregatedStats:
        """Получение статистики"""
        # Используем hash от записей для инвалидации кэша
        records = self._get_records_snapshot()
        records_hash = hash(records)

        return self._calculate_stats(records_hash)

    def get_extended_stats(self) -> Dict[str, Any]:
        """Расширенная статистика"""
        stats = self.get_stats()

        # Дополнительные метрики
        uptime = time.time() - self._start_time
        requests_per_second = self._total_counter / uptime if uptime > 0 else 0

        success_rate = (
            (self._success_counter / self._total_counter * 100)
            if self._total_counter > 0 else 0
        )

        return {
            "basic_stats": stats.to_dict(),
            "extended_metrics": {
                "total_requests_processed": self._total_counter,
                "successful_requests": self._success_counter,
                "failed_requests": self._total_counter - self._success_counter,
                "success_rate_percent": round(success_rate, 2),
                "requests_per_second": round(requests_per_second, 3),
                "uptime_seconds": round(uptime, 2),
                "window_size": len(self._records),
                "window_max_size": self.max_records
            }
        }

    def reset_stats(self):
        """Сброс статистики"""
        self._records.clear()
        self._total_counter = 0
        self._success_counter = 0
        self._start_time = time.time()
        self._invalidate_cache()
