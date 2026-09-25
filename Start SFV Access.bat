@echo off
cd /d "%~dp0"
rem A copy installed for players carries its own Python, kept to its own
rem packages by -E and -s; a development copy has a virtual environment.
if exist "python\python.exe" (
    "python\python.exe" -E -s run.py
) else (
    ".venv\Scripts\python.exe" run.py
)
rem Quitting with F10 closes this window. If the mod stopped with an error,
rem stay open so the message can be read.
if errorlevel 1 pause
