$root = "C:\Users\Archer\SC-NEW\taiga-qc-tracker"

Start-Process powershell -WindowStyle Hidden -ArgumentList @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-Command",
  "Set-Location '$root\backend'; python -m uvicorn app.main:app --port 8000 *> '$root\backend-runtime.log'"
)

Start-Sleep -Seconds 2

Start-Process powershell -WindowStyle Hidden -ArgumentList @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-Command",
  "Set-Location '$root\frontend'; npm run dev *> '$root\frontend-runtime.log'"
)

Start-Sleep -Seconds 5
Start-Process "http://localhost:5173"
