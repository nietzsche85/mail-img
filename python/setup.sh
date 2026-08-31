#!/usr/bin/env bash
# macOS / Linux 설치 스크립트.  사용법:  bash setup.sh
set -uo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
VENVPY=".venv/bin/python"

echo "▸ [1/6] 파이썬 확인"
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
  echo "  [X] Python 3.10 이상이 필요합니다 (현재: $("$PY" --version 2>&1))"
  exit 1
fi
"$PY" --version

echo "▸ [2/6] 가상환경 만들기 (.venv)"
[ -x "$VENVPY" ] || "$PY" -m venv .venv
if [ ! -x "$VENVPY" ]; then
  echo "  [X] 가상환경을 만들지 못했습니다."
  exit 1
fi

echo "▸ [3/6] 라이브러리 설치"
# activate 에 기대지 않고 venv 의 python 을 직접 부릅니다.
# 활성화가 안 된 상태에서 설치되면 시스템 파이썬으로 새어 들어갑니다.
"$VENVPY" -m pip install --quiet --upgrade pip
if [ -d vendor/wheels ]; then
  echo "  (동봉된 wheel 사용 — 인터넷 불필요)"
  "$VENVPY" -m pip install --quiet --no-index --find-links vendor/wheels -r requirements.txt
else
  "$VENVPY" -m pip install --quiet -r requirements.txt
fi
if [ $? -ne 0 ]; then
  echo "  [X] 라이브러리 설치에 실패했습니다."
  echo "      수동 설치: $VENVPY -m pip install -r requirements.txt"
  exit 1
fi

echo "▸ [4/6] 설치 확인"
if ! "$VENVPY" -c "import anthropic, playwright, yaml, requests, bs4, lxml, imageio_ffmpeg, pydantic; print('  모든 라이브러리 정상')"; then
  echo "  [X] 라이브러리가 제대로 안 깔렸습니다."
  exit 1
fi

echo "▸ [5/6] Chromium 내려받기"
# 사내망·방화벽에서 자주 막힙니다. 실패해도 설치를 중단하지 않습니다.
if "$VENVPY" -m playwright install chromium; then
  BROWSER_OK=1
else
  BROWSER_OK=0
  echo "  [!] Chromium 을 못 받았습니다 (네트워크 차단일 수 있습니다)."
  echo "      나중에 다시:  $VENVPY -m playwright install chromium"
  echo "      이미 크롬이 있다면:  export CHROMIUM_PATH=/크롬/실행/경로"
fi

[ -f .env ] || cp .env.example .env

echo "▸ [6/6] 환경 점검"
"$VENVPY" -m sns_autopilot doctor || true
[ "$BROWSER_OK" = "1" ] || echo "  [!] 위 Chromium 항목은 브라우저를 받은 뒤 다시 통과합니다."

cat <<MSG

────────────────────────────────────────────────
 설치 끝.

 1) .env 파일을 열어 ANTHROPIC_API_KEY 를 채우세요
    $(pwd)/.env

 2) 실행
    source .venv/bin/activate
    python -m sns_autopilot capture --flow config/flows/demo.yaml
    python -m sns_autopilot copy --latest
────────────────────────────────────────────────
MSG
