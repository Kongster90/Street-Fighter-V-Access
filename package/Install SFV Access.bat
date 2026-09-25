@echo off
rem Once the mod is installed, the extracted folder keeps only this file, the
rem uninstaller and the text files, so run the installed copy's installer from
rem there, which asks again whether to start with the game.
set "SFV=%~dp0"
if not exist "%SFV%python\python.exe" set "SFV=%LOCALAPPDATA%\Programs\SFV Access\"
if not exist "%SFV%python\python.exe" (
    echo The mod's files are not in this folder, and it is not installed. Extract the zip again, then run Install SFV Access from the new folder.
    pause
    exit /b 1
)
cd /d "%SFV%"
"python\python.exe" -E -s tools\install.py
if errorlevel 1 pause
