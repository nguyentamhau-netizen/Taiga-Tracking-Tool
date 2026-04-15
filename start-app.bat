@echo off
setlocal
set ROOT=%~dp0

if not exist "%ROOT%config.local.json" (
  echo Missing config.local.json
  echo Copy config.example.json to config.local.json first.
  pause
  exit /b 1
)

if not exist "%ROOT%frontend\dist\index.html" (
  call "%ROOT%build-frontend.bat"
  if errorlevel 1 exit /b 1
)

cd /d "%ROOT%backend"
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
)
call ".venv\Scripts\python.exe" -m pip install -e . >nul

start "Taiga QC Tracker" "%ROOT%backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
timeout /t 3 >nul
start http://127.0.0.1:8000

endlocal
