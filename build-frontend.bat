@echo off
setlocal
set ROOT=%~dp0

cd /d "%ROOT%frontend"
if not exist node_modules (
  call npm install
)
call npm run build

endlocal
