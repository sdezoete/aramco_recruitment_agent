@echo off
rem Start the Recruitment Agent with the settings in .env (HTTPS when PRODUCTION=True).
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo .venv missing. Run: powershell -ExecutionPolicy Bypass -File scripts\2-install-offline.ps1
  exit /b 1
)
".venv\Scripts\python.exe" -m app
