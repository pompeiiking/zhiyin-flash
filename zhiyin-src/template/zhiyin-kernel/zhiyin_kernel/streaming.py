"""Request-local progress channel. No global subscriber or cross-account state."""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable

_sink: ContextVar[Callable[[dict], None] | None] = ContextVar("progress_sink", default=None)


@contextmanager
def progress_channel(sink: Callable[[dict], None]):
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)


def is_streaming() -> bool:
    return _sink.get() is not None


def emit_progress(frame: dict) -> None:
    sink = _sink.get()
    if sink is not None:
        sink(frame)
