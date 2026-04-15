@echo off
setlocal
set ROOT=%~dp0
set DIST_NAME=TaigaQCTracker
set RELEASE_DIR=%ROOT%release
set PORTABLE_DIR=%RELEASE_DIR%\%DIST_NAME%-portable

cd /d "%ROOT%frontend"
if not exist node_modules (
  call npm install
)
call npm run build
if errorlevel 1 exit /b 1

cd /d "%ROOT%"
pyinstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name "%DIST_NAME%" ^
  --icon "%ROOT%assets\\taiga-qc-tracker.ico" ^
  --paths "%ROOT%backend" ^
  --add-data "%ROOT%frontend\\dist;frontend\\dist" ^
  --add-data "%ROOT%config.example.json;." ^
  "%ROOT%backend\\run_portable.py"
if errorlevel 1 exit /b 1

copy /y "%ROOT%config.example.json" "%ROOT%dist\\%DIST_NAME%\\config.example.json" >nul

if exist "%PORTABLE_DIR%" rmdir /s /q "%PORTABLE_DIR%"
mkdir "%PORTABLE_DIR%"

xcopy /e /i /y "%ROOT%dist\\%DIST_NAME%\\*" "%PORTABLE_DIR%\\" >nul

if exist "%RELEASE_DIR%\\%DIST_NAME%-portable.zip" del /f /q "%RELEASE_DIR%\\%DIST_NAME%-portable.zip"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%PORTABLE_DIR%\\*' -DestinationPath '%RELEASE_DIR%\\%DIST_NAME%-portable.zip' -Force"

echo Portable build ready:
echo %RELEASE_DIR%\%DIST_NAME%-portable.zip

endlocal
