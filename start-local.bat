@echo off
set ROOT=C:\Users\Archer\SC-NEW\taiga-qc-tracker

start "Taiga QC Tracker Backend" cmd /k "cd /d %ROOT%\backend && python -m uvicorn app.main:app --port 8000"
start "Taiga QC Tracker Frontend" cmd /k "cd /d %ROOT%\frontend && npm run dev"

timeout /t 5 >nul
start http://localhost:5173
