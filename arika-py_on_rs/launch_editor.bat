@echo off
setlocal
rem Build the arika_backend shared library if needed
if not exist "%~dp0arika_backend.dll" (
    echo Building arika_backend.dll...
    py -3 "%~dp0build.py"
    if errorlevel 1 exit /b %errorlevel%
)
py -3 "%~dp0arika_editor.py" %*