$root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path "$root\config.local.json")) {
  Write-Host "Missing config.local.json"
  Write-Host "Copy config.example.json to config.local.json first."
  pause
  exit 1
}

if (-not (Test-Path "$root\frontend\dist\index.html")) {
  & "$root\build-frontend.bat"
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Set-Location "$root\backend"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  py -3 -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install -e . | Out-Null

Start-Process powershell -WindowStyle Hidden -ArgumentList @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-Command",
  "Set-Location '$root\backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 *> '$root\backend-runtime.log'"
)

Start-Sleep -Seconds 3
Start-Process "http://127.0.0.1:8000"
