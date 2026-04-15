Set WshShell = CreateObject("WScript.Shell")
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""C:\Users\Archer\SC-NEW\taiga-qc-tracker\start-app.ps1"""
WshShell.Run command, 0, False
