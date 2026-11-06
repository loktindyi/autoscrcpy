@echo off
setlocal
cd /d "%~dp0"
echo Starting AutoScrcpy with a visible console...
echo DevTools enabled: press F12 in the UI (Ctrl+Shift+I may be taken by another app),
echo or right-click and choose Inspect.
echo Use the top-right window button, the window close button or the tray icon to quit.
echo.
python app.py --verbose --devtools %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo AutoScrcpy exited with code %RC%.
  pause
)
exit /b %RC%
