"""설정(YAML) 로딩, .env 읽기, ${ENV} 치환."""
from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any

import yaml

from .paths import ROOT

_ENV_REF = re.compile(r"\$\{([A-Za-z0-9_]+)\}")

DEFAULTS: dict[str, Any] = {
    "brand": {"name": "브랜드", "voice": "친근하고 구체적으로", "banned": [], "cta": "", "colors": {}},
    "capture": {"flow": "config/flows/demo.yaml"},
    "render": {
        "shorts": {
            "width": 1080, "height": 1920, "fps": 30, "maxDuration": 28,
            "speed": "auto", "bgm": "",
            "intro": {"text": "", "image": "", "seconds": 1.6},
            "outro": {"text": "", "image": "", "seconds": 2.0},
        },
        "gif": {"width": 640, "fps": 12, "maxDuration": 8},
    },
    "blog": {"feed": "", "urls": [], "limit": 3, "stateFile": ".state/seen.json"},
    "copy": {
        "model": "claude-opus-5", "effort": "high",
        "platforms": ["instagram", "threads", "x"], "variants": 2, "language": "ko",
    },
    "image": {"template": "templates/card.html", "sizes": [{"name": "feed", "width": 1080, "height": 1350}]},
    "publish": {"targets": ["file"], "scheduleAt": ""},
}


def load_env(file: Path | None = None) -> None:
    """.env 를 아주 단순하게 읽어 환경변수에 채웁니다 (이미 있는 값은 덮어쓰지 않음)."""
    path = file or ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def expand_env(value: Any) -> Any:
    """문자열 안의 ${VAR} 을 환경변수로 치환합니다. 없으면 빈 문자열."""
    if isinstance(value, str):
        return _ENV_REF.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    return value


def resolve(file: Path | str) -> Path:
    path = Path(file)
    return path if path.is_absolute() else ROOT / path


def load_yaml(file: Path | str) -> dict[str, Any]:
    path = resolve(file)
    if not path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {path}")
    return expand_env(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def _deep_merge(base: Any, override: Any) -> Any:
    if override is None:
        return base
    if isinstance(override, list):
        return override
    if not isinstance(override, dict) or not isinstance(base, dict):
        return override
    merged = dict(base)
    for key, value in override.items():
        merged[key] = _deep_merge(base.get(key), value)
    return merged


def load_config(file: Path | str = "config/pipeline.yaml") -> dict[str, Any]:
    load_env()
    return _deep_merge(copy.deepcopy(DEFAULTS), load_yaml(file))
