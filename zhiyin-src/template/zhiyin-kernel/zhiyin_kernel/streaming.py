"""Request-local progress channel. No global subscriber or cross-account state."""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable

_sink: ContextVar[Callable[[dict], None] | None] = ContextVar("progress_sink", default=None)
_cancel_check: ContextVar[Callable | None] = ContextVar("run_cancel_check", default=None)


@contextmanager
def cancellation_channel(check):
    token = _cancel_check.set(check)
    try:
        yield
    finally:
        _cancel_check.reset(token)


async def cancellation_requested():
    check = _cancel_check.get()
    return bool(await check()) if check else False


@contextmanager
def progress_channel(sink: Callable[[dict], None]):
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)


@contextmanager
def capture_progress(capture):
    """Observe and envelope events without replacing the caller's subscriber."""
    parent = _sink.get()
    def forward(frame):
        capture(frame)
        if parent is not None:
            parent(frame)
    token = _sink.set(forward)
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
