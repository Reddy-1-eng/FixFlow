@echo off
title BuildFail-SLM Launcher
cd /d "%~dp0"

IF EXIST ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run.py
) ELSE (
    python run.py
)

pause
