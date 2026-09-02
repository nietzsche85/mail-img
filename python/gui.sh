#!/usr/bin/env bash
# macOS / Linux 에서 창 띄우기.  사용법:  bash gui.sh
cd "$(dirname "$0")"
VENVPY=".venv/bin/python"
if [ ! -x "$VENVPY" ]; then
  echo "[X] 아직 설치가 안 됐습니다. 먼저 bash setup.sh 를 실행해주세요."
  exit 1
fi
exec "$VENVPY" -m sns_autopilot gui
