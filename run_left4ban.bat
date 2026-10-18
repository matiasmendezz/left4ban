@echo off
setlocal
title Left 4 Ban

cd /d "%~dp0"

if exist "dist\Left4Ban.exe" (
    echo [Left4Ban] Launching standalone executable...
    start "" "dist\Left4Ban.exe"
    exit /b
)

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PYTHON=venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

echo [Left4Ban] Starting Left 4 Ban web application...
"%PYTHON%" app.py

pause
