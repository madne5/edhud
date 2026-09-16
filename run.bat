@echo off
REM elite-hud launcher for Windows.
REM
REM First run creates a virtual environment and installs PySide6, then starts
REM the overlay. Later runs skip straight to launching.
REM
REM Run this file by double-clicking it, or from a terminal:
REM     run.bat
REM     run.bat --headless --replay "tests\fixtures\Journal.2026-03-14T200000.01.log"

setlocal
cd /d "%~dp0"

set "PYTHON=py -3"
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    set "PYTHON=python"
    %PYTHON% --version >nul 2>&1
    if errorlevel 1 (
        echo [elite-hud] Python 3 was not found on PATH.
        echo             Install it from https://www.python.org/downloads/windows/
        echo             and tick "Add python.exe to PATH" during setup.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo [elite-hud] Creating virtual environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo [elite-hud] Could not create the virtual environment.
        pause
        exit /b 1
    )
    echo [elite-hud] Installing PySide6 ^(about 150 MB, one time^)...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [elite-hud] Dependency installation failed.
        pause
        exit /b 1
    )
)

set "PYTHONPATH=%CD%"
".venv\Scripts\python.exe" -m elite_hud %*
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
    echo.
    echo [elite-hud] Exited with code %EXITCODE%.
    pause
)
endlocal & exit /b %EXITCODE%
