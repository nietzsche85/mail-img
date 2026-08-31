"""터미널 로그. GUI 에서는 sink 를 걸어 창 안으로 보냅니다."""
from __future__ import annotations

import sys
from datetime import datetime
from typing import Callable

_RESET = "\033[0m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"

_color = bool(getattr(sys.stdout, "isatty", lambda: False)())

#: 설정되면 터미널 대신 이쪽으로 (kind, message) 가 전달됩니다.
_sink: Callable[[str, str], None] | None = None


def set_sink(sink: Callable[[str, str], None] | None) -> None:
    """GUI 등 다른 화면으로 로그를 돌립니다. None 이면 다시 터미널로."""
    global _sink
    _sink = sink


def _paint(code: str, text: str) -> str:
    return f"{code}{text}{_RESET}" if _color else text


def _write(line: str, stream=None) -> None:
    target = stream or sys.stdout
    if target is None:      # pythonw 로 띄우면 stdout 이 없습니다
        return
    print(line, file=target, flush=True)


def step(message: str) -> None:
    if _sink:
        return _sink("step", message)
    _write(f"{_paint(_CYAN, '▸')} {message}")


def info(message: str) -> None:
    if _sink:
        return _sink("info", message)
    stamp = datetime.now().strftime("%H:%M:%S")
    _write(f"{_paint(_DIM, stamp)} {message}")


def ok(message: str) -> None:
    if _sink:
        return _sink("ok", message)
    _write(f"{_paint(_GREEN, '✓')} {message}")


def warn(message: str) -> None:
    if _sink:
        return _sink("warn", message)
    _write(f"{_paint(_YELLOW, '!')} {message}", sys.stderr)


def error(message: str) -> None:
    if _sink:
        return _sink("error", message)
    _write(f"{_paint(_RED, '✗')} {message}", sys.stderr)
