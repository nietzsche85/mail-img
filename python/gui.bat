@echo off
REM 더블클릭하면 창이 뜹니다.  (CRLF 줄바꿈 필수)
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "VENVPY=.venv\Scripts\python.exe"
set "VENVPYW=.venv\Scripts\pythonw.exe"

if not exist "%VENVPY%" goto :nosetup

REM pythonw 로 띄우면 오류가 안 보여서, 먼저 콘솔 파이썬으로 불러올 수 있는지 봅니다.
"%VENVPY%" -c "import sns_autopilot.gui" 2>nul
if errorlevel 1 goto :importfail

if exist "%VENVPYW%" (
  start "" "%VENVPYW%" -m sns_autopilot gui
) else (
  "%VENVPY%" -m sns_autopilot gui
)
goto :eof

:nosetup
echo.
echo [X] 아직 설치가 안 됐습니다. 먼저 setup.bat 을 실행해주세요.
echo.
pause
goto :eof

:importfail
echo.
echo [X] 창을 띄우지 못했습니다. 자세한 원인:
echo.
"%VENVPY%" -c "import sns_autopilot.gui"
echo.
echo   라이브러리가 없다면: .venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
pause
