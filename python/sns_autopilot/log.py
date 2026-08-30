"""터미널 로그. 색만 입히는 얇은 래퍼입니다."""
from __future__ import annotations

import sys
from datetime import datetime

_RESET = "\033[0m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"

_color = sys.stdout.isatty()


def _paint(code: str, text: str) -> str:
    return f"{code}{text}{_RESET}" if _color else text


def step(message: str) -> None:
    print(f"{_paint(_CYAN, '▸')} {message}", flush=True)


def info(message: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"{_paint(_DIM, stamp)} {message}", flush=True)


def ok(message: str) -> None:
    print(f"{_paint(_GREEN, '✓')} {message}", flush=True)


def warn(message: str) -> None:
    print(f"{_paint(_YELLOW, '!')} {message}", file=sys.stderr, flush=True)


def error(message: str) -> None:
    print(f"{_paint(_RED, '✗')} {message}", file=sys.stderr, flush=True)
