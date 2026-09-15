@echo off
cd /d "%~dp0"
"python\python.exe" tools\uninstall.py
if errorlevel 1 pause
