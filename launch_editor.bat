@echo off
setlocal
rem Build the arika_backend shared library if needed
if not exist "%~dp0arika-py_on_rs\arika_backend.dll" (
    echo Building arika_backend.dll...
    py -3 "%~dp0arika-py_on_rs\build.py"
    if errorlevel 1 exit /b %errorlevel%
)
py -3 "%~dp0arika-py_on_rs\arika_editor.py" %*