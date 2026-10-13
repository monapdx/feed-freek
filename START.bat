@echo off
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 app.py
) else (
  where python >nul 2>nul
  if not errorlevel 1 (
    python app.py
  ) else (
    echo Python 3 is required. Install it and enable Add Python to PATH.
  )
)
pause
