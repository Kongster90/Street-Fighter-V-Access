@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py
rem Quitting with F10 closes this window. If the mod stopped with an error,
rem stay open so the message can be read.
if errorlevel 1 pause
