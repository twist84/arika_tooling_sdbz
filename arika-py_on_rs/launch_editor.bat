@echo off
setlocal
rem Always run Cargo's incremental build before importing ctypes exports.
py -3 "%~dp0build.py"
if errorlevel 1 exit /b 1
py -3 "%~dp0arika_editor.py" %*
exit /b %errorlevel%
