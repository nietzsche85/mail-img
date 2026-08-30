#!/usr/bin/env bash
# macOS / Linux 설치 스크립트.  사용법:  bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
echo "▸ 파이썬 확인"
"$PY" -c 'import sys; assert sys.version_info >= (3,10), f"Python 3.10 이상이 필요합니다 (현재 {sys.version.split()[0]})"'
"$PY" --version

echo "▸ 가상환경 만들기 (.venv)"
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "▸ 라이브러리 설치"
python -m pip install --quiet --upgrade pip
if [ -d vendor/wheels ]; then
  echo "  (동봉된 wheel 사용 — 인터넷 불필요)"
  python -m pip install --quiet --no-index --find-links vendor/wheels -r requirements.txt
else
  python -m pip install --quiet -r requirements.txt
fi

# 브라우저 내려받기는 사내망·방화벽에서 막히는 일이 잦습니다.
# 여기서 실패해도 나머지 설치는 끝내고, 무엇을 다시 하면 되는지 알려줍니다.
echo "▸ Chromium 내려받기"
if python -m playwright install chromium; then
  BROWSER_OK=1
else
  BROWSER_OK=0
  echo "  ! Chromium 을 못 받았습니다 (네트워크 차단일 수 있습니다)."
  echo "    나중에 다시:  source .venv/bin/activate && python -m playwright install chromium"
  echo "    이미 크롬이 있다면:  export CHROMIUM_PATH=/크롬/실행/경로"
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "▸ .env 를 만들었습니다 — ANTHROPIC_API_KEY 를 채워주세요: $(pwd)/.env"
fi

echo "▸ 환경 점검"
python -m sns_autopilot doctor || true
[ "$BROWSER_OK" = "1" ] || echo "  ! 위 Chromium 항목은 브라우저를 받은 뒤 다시 통과합니다."

cat <<'MSG'

────────────────────────────────────────────────
설치 끝. 다음부터는 이렇게 쓰시면 됩니다.

  source .venv/bin/activate
  python -m sns_autopilot capture --flow config/flows/demo.yaml
  python -m sns_autopilot copy --latest
────────────────────────────────────────────────
MSG
