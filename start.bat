@echo off
cd /d "%~dp0"
python --version >nul 2>&1 || (echo Python is not installed. Get it free at https://www.python.org/downloads/ ^(tick "Add to PATH"^), then run this again. & pause & exit /b)
if not exist ".setup_done" (
  echo First run: installing what the tool needs, one time only...
  python -m pip install -r requirements.txt && python -m playwright install chromium && echo ok> .setup_done
)
python start.py
pause
