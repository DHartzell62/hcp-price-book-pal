@echo off
cd /d "%~dp0"
python --version >nul 2>&1 || (echo Python is not installed. Get it free at https://www.python.org/downloads/ ^(tick "Add to PATH"^), then run this again. & pause & exit /b)
rem Install (again) whenever requirements.txt differs from what was last installed, so upgrades get new packages.
fc /b requirements.txt .setup_done >nul 2>&1
if errorlevel 1 (
  echo Installing what the tool needs. This can take a few minutes...
  python -m pip install -r requirements.txt && python -m playwright install chromium && copy /y requirements.txt .setup_done >nul
)
python start.py
pause
