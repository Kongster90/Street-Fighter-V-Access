@echo off
cd /d "%~dp0"
"python\python.exe" tools\install.py
if errorlevel 1 pause
