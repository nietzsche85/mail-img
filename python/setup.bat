@echo off
REM Windows 설치 스크립트.  사용법:  setup.bat
setlocal
cd /d "%~dp0"

echo. & echo [1/5] 파이썬 확인
python -c "import sys; assert sys.version_info >= (3,10), 'Python 3.10 이상이 필요합니다'" || goto :fail
python --version

echo. & echo [2/5] 가상환경 만들기 (.venv)
if not exist .venv python -m venv .venv || goto :fail
call .venv\Scripts\activate.bat

echo. & echo [3/5] 라이브러리 설치
python -m pip install --quiet --upgrade pip
if exist vendor\wheels (
  echo   ^(동봉된 wheel 사용 - 인터넷 불필요^)
  python -m pip install --quiet --no-index --find-links vendor\wheels -r requirements.txt || goto :fail
) else (
  python -m pip install --quiet -r requirements.txt || goto :fail
)

REM 브라우저 내려받기는 사내망/방화벽에서 막히는 일이 잦습니다.
REM 여기서 실패해도 나머지 설치는 끝내고, 무엇을 다시 하면 되는지 알려줍니다.
echo. & echo [4/5] Chromium 내려받기
python -m playwright install chromium
if errorlevel 1 (
  echo   [!] Chromium 을 못 받았습니다 ^(네트워크 차단일 수 있습니다^).
  echo       나중에 다시:  .venv\Scripts\activate ^&^& python -m playwright install chromium
  echo       이미 크롬이 있다면:  set CHROMIUM_PATH=C:\경로\chrome.exe
)

if not exist .env (
  copy /y .env.example .env >nul
  echo. & echo [!] .env 를 만들었습니다 - ANTHROPIC_API_KEY 를 채워주세요: %cd%\.env
)

echo. & echo [5/5] 환경 점검
python -m sns_autopilot doctor

echo.
echo ------------------------------------------------
echo 설치 끝. 다음부터는 이렇게 쓰시면 됩니다.
echo.
echo   .venv\Scripts\activate
echo   python -m sns_autopilot capture --flow config/flows/demo.yaml
echo   python -m sns_autopilot copy --latest
echo ------------------------------------------------
goto :eof

:fail
echo.
echo [X] 설치 중 오류가 났습니다. 위 메시지를 확인해주세요.
exit /b 1
