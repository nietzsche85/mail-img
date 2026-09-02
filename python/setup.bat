@echo off
REM Windows 설치 스크립트.  사용법: setup.bat  (더블클릭 가능)
REM 이 파일은 반드시 CRLF 줄바꿈이어야 합니다. cmd.exe 가 LF 파일의
REM 라벨과 괄호 블록을 잘못 읽어 설치가 조용히 어긋납니다.
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0"

set "PY=python"
set "VENVPY=.venv\Scripts\python.exe"

echo.
echo [1/6] 파이썬 확인
%PY% --version
if errorlevel 1 goto :nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 goto :oldpython

echo.
echo [2/6] 가상환경 만들기 (.venv)
if not exist "%VENVPY%" %PY% -m venv .venv
if not exist "%VENVPY%" goto :novenv

echo.
echo [3/6] 라이브러리 설치
REM activate 에 기대지 않고 venv 의 python 을 직접 부릅니다.
REM 활성화가 안 된 상태에서 설치되면 시스템 파이썬으로 새어 들어갑니다.
"%VENVPY%" -m pip install --quiet --upgrade pip
if exist "vendor\wheels" goto :offline
"%VENVPY%" -m pip install -r requirements.txt
if errorlevel 1 goto :pipfail
goto :browser

:offline
echo   (동봉된 wheel 사용 - 인터넷 불필요)
"%VENVPY%" -m pip install --no-index --find-links vendor\wheels -r requirements.txt
if errorlevel 1 goto :pipfail

:browser
echo.
echo [4/6] 설치 확인
"%VENVPY%" -c "import anthropic, playwright, yaml, requests, bs4, lxml, imageio_ffmpeg, pydantic; print('   모든 라이브러리 정상')"
if errorlevel 1 goto :pipfail

echo.
echo [5/6] Chromium 내려받기
REM 사내망/방화벽에서 자주 막힙니다. 실패해도 설치를 중단하지 않습니다.
"%VENVPY%" -m playwright install chromium
if errorlevel 1 echo   [!] Chromium 을 못 받았습니다. 나중에 다시: .venv\Scripts\python.exe -m playwright install chromium

if not exist ".env" copy /y .env.example .env >nul
if not exist ".env" goto :envfail

echo.
echo [6/6] 환경 점검
"%VENVPY%" -m sns_autopilot doctor

echo.
echo ================================================
echo  설치 끝.
echo.
echo  1) .env 파일을 열어 ANTHROPIC_API_KEY 를 채우세요
echo     %cd%\.env
echo.
echo  2) 창으로 쓰기 - gui.bat 을 더블클릭하세요
echo.
echo  3) 명령줄로 쓰기
echo     .venv\Scripts\activate
echo     python -m sns_autopilot capture --url https://내홈페이지.com
echo     python -m sns_autopilot copy --latest
echo ================================================
goto :done

:nopython
echo   [X] python 을 찾을 수 없습니다. python.org 에서 설치하고
echo       설치 화면의 'Add python.exe to PATH' 를 체크하세요.
goto :done

:oldpython
echo   [X] Python 3.10 이상이 필요합니다.
goto :done

:novenv
echo   [X] 가상환경을 만들지 못했습니다. python -m venv .venv 를 직접 실행해보세요.
goto :done

:pipfail
echo   [X] 라이브러리 설치에 실패했습니다. 위 메시지를 확인해주세요.
echo       수동 설치: .venv\Scripts\python.exe -m pip install -r requirements.txt
goto :done

:envfail
echo   [X] .env 를 만들지 못했습니다. .env.example 을 .env 로 직접 복사해주세요.

:done
echo.
pause
