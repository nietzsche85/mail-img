"""ffmpeg 실행 래퍼. 파이썬 휠에 들어 있는 정적 바이너리를 우선 씁니다."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from . import log

_TIME = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)")


@lru_cache(maxsize=1)
def binary() -> str:
    if os.environ.get("FFMPEG_PATH"):
        return os.environ["FFMPEG_PATH"]
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 - 없으면 시스템 ffmpeg 로 넘어갑니다
        pass
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("ffmpeg 을 찾을 수 없습니다. pip install imageio-ffmpeg 를 실행하세요.")
    return found


def run(args: list[str], quiet: bool = True) -> str:
    cmd = [binary(), "-hide_banner", "-loglevel", "error" if quiet else "info", "-y", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        log.error("\n".join(result.stderr.splitlines()[-25:]))
        raise RuntimeError(f"ffmpeg 종료 코드 {result.returncode}")
    return result.stderr


def duration(file: Path | str) -> float:
    """ffprobe 없이 ffmpeg 만으로 길이를 잽니다.

    컨테이너 헤더의 Duration 을 먼저 봅니다. 진행 로그(time=)는 마지막 줄이
    실제 끝보다 앞설 수 있어서, 그걸로 자르면 영상 뒷부분이 날아갑니다.
    """
    try:
        stderr = run(["-i", str(file), "-f", "null", "-"], quiet=False)
    except RuntimeError:
        return 0.0

    for pattern in (_DURATION, _TIME):
        matches = pattern.findall(stderr)
        if matches:
            hours, minutes, seconds = matches[-1] if pattern is _TIME else matches[0]
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return 0.0
