"""python -m sns_autopilot 진입점."""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from .cli import main
except ImportError as exc:  # 라이브러리 미설치 — 파이썬 역추적 대신 할 일을 알려줍니다.
    missing = getattr(exc, "name", None) or "필요한 라이브러리"
    in_venv = sys.prefix != sys.base_prefix
    root = Path(__file__).resolve().parents[1]
    venv_python = root / (".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python")

    print(f"✗ '{missing}' 라이브러리가 없습니다.", file=sys.stderr)
    print(file=sys.stderr)
    if not in_venv:
        print("  지금 가상환경(.venv) 밖의 파이썬으로 실행 중입니다.", file=sys.stderr)
        print("  설치 스크립트를 한 번 돌리시면 한 번에 정리됩니다:", file=sys.stderr)
        print(f"      {'setup.bat' if sys.platform == 'win32' else 'bash setup.sh'}", file=sys.stderr)
        print(file=sys.stderr)
    print("  직접 설치하려면:", file=sys.stderr)
    print(f'      "{venv_python}" -m pip install -r requirements.txt', file=sys.stderr)
    raise SystemExit(1) from None

if __name__ == "__main__":
    raise SystemExit(main())
