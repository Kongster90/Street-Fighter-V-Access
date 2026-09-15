@echo off
cd /d "%~dp0"
rem A copy installed for players carries its own Python; a development copy has
rem a virtual environment.
if exist "python\python.exe" (
    "python\python.exe" run.py
) else (
    ".venv\Scripts\python.exe" run.py
)
rem Quitting with F10 closes this window. If the mod stopped with an error,
rem stay open so the message can be read.
if errorlevel 1 pause
