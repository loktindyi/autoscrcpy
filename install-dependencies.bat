@echo off
setlocal
cd /d "%~dp0"
echo Installing Python dependencies for AutoScrcpy...
python -m pip install -r requirements.txt
echo.
pause
