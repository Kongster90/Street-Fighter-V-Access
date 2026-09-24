@echo off
rem Uninstall the installed copy, whether this is its own file or the one left
rem in the extracted folder.
set "SFV=%LOCALAPPDATA%\Programs\SFV Access\"
if not exist "%SFV%python\python.exe" set "SFV=%~dp0"
if not exist "%SFV%python\python.exe" (
    echo Street Fighter V Access is not installed, so there is nothing to uninstall.
    pause
    exit /b 1
)
cd /d "%SFV%"
"python\python.exe" tools\uninstall.py
if errorlevel 1 pause
