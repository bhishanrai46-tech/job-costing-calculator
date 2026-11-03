@echo off
setlocal
cd /d "%~dp0"

rem Pick whichever Python launcher is installed
set "PY=python"
where python >nul 2>nul || set "PY=py"
where %PY% >nul 2>nul || (
  echo Python was not found. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" in the installer.
  pause
  exit /b 1
)

rem Install the PDF tool the first time only
%PY% -c "import reportlab" >nul 2>nul || (
  echo Installing the PDF tool, one moment...
  %PY% -m pip install --quiet reportlab
)

rem Start the app without leaving a black window open
if "%PY%"=="py" (
  start "" pyw "job_costing_app.py"
) else (
  start "" pythonw "job_costing_app.py"
)
