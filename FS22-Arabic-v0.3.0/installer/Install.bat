@echo off
set PY=
where py >nul 2>nul && set PY=py
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY (
    echo   Python is not installed. Install it, tick "Add python.exe to PATH", then run this again.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)
%PY% "%~dp0install.py" %*
pause
