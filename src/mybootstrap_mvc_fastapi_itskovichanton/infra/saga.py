"""Оркестрация saga: шаги + компенсации (spring-like декораторы)."""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


class SagaContext:
    """Контекст одной saga: стек компенсаций (LIFO при откате)."""

    def __init__(self, name: str = "saga"):
        self.name = name
        self._compensations: list[Callable[[], Awaitable[None]]] = []
        self.aborted = False

    def on_compensate(self, fn: Callable[[], Awaitable[None]]) -> None:
        self._compensations.append(fn)

    async def compensate_all(self) -> None:
        self.aborted = True
        for fn in reversed(self._compensations):
            try:
                await fn()
            except Exception:
                logger.exception("Saga %s: compensation failed", self.name)


def saga(name: str | None = None):
    """
    Декоратор use-case: при исключении откатывает все зарегистрированные компенсации.

        @saga("register.verify")
        async def execute(self, ..., saga_ctx: SagaContext | None = None):
            ...
    """

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> R:
            ctx = kwargs.get("saga_ctx")
            if ctx is None:
                ctx = SagaContext(name or fn.__qualname__)
                kwargs["saga_ctx"] = ctx
            try:
                return await fn(*args, **kwargs)
            except Exception:
                await ctx.compensate_all()
                raise

        return wrapper  # type: ignore[return-value]

    return decorator


def saga_step(compensate: Callable[..., Awaitable[None]] | None = None):
    """
    Декоратор шага: после успеха регистрирует compensate(result, *args, **kwargs).

    compensate получает результат шага первым аргументом.
    """

    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> R:
            ctx: SagaContext | None = kwargs.get("saga_ctx")
            result = await fn(*args, **kwargs)
            if ctx is not None and compensate is not None and not ctx.aborted:

                async def _comp() -> None:
                    await compensate(result, *args, **kwargs)

                ctx.on_compensate(_comp)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator
