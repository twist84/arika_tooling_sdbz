@echo off
setlocal
rem Cargo rebuilds only when Rust sources or dependencies have changed.
rem Checking only if the DLL exists can leave an incompatible binary.
py -3 "%~dp0arika-py_on_rs\build.py"
if errorlevel 1 exit /b 1
py -3 "%~dp0arika-py_on_rs\arika_editor.py" %*
exit /b %errorlevel%
