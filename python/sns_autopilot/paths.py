"""실행 폴더 구조와 JSON 입출력 헬퍼."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"

_RUN_ID = re.compile(r"^\d{8}-\d{6}$")


@dataclass(frozen=True)
class RunPaths:
    """out/<실행ID>/ 아래에 이번 실행의 모든 산출물이 모입니다."""

    run_id: str
    base: Path
    capture: Path
    render: Path
    images: Path
    copy: Path
    queue: Path

    @classmethod
    def create(cls, run_id: str) -> "RunPaths":
        base = OUT_DIR / run_id
        paths = cls(
            run_id=run_id,
            base=base,
            capture=base / "capture",
            render=base / "render",
            images=base / "images",
            copy=base / "copy",
            queue=base / "queue",
        )
        for directory in (paths.base, paths.capture, paths.render, paths.images, paths.copy, paths.queue):
            directory.mkdir(parents=True, exist_ok=True)
        return paths

    @property
    def manifest(self) -> Path:
        return self.base / "manifest.json"


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def latest_run() -> str | None:
    if not OUT_DIR.exists():
        return None
    runs = sorted(d.name for d in OUT_DIR.iterdir() if d.is_dir() and _RUN_ID.match(d.name))
    return runs[-1] if runs else None


def read_json(file: Path | str, fallback: Any = None) -> Any:
    try:
        return json.loads(Path(file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def write_json(file: Path | str, data: Any) -> Path:
    path = Path(file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def relative(path: Path | str) -> str:
    """로그에 찍을 때 짧게 보이도록."""
    try:
        return str(Path(path).relative_to(Path.cwd()))
    except ValueError:
        return str(path)
