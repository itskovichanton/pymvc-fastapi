"""Утилита: сохранить сигнатуру хендлера для FastAPI DI."""

from __future__ import annotations

import functools
import inspect
from typing import Callable


def preserve_signature(wrapper: Callable, wrapped: Callable) -> Callable:
    functools.update_wrapper(wrapper, wrapped)
    try:
        wrapper.__signature__ = inspect.signature(wrapped)  # type: ignore[attr-defined]
    except (TypeError, ValueError):
        pass
    return wrapper
