@echo off
setlocal EnableExtensions
chcp 65001 >nul
title AutoScrcpy 一键提交
cd /d "%~dp0"

rem ============================================================
rem  AutoScrcpy 一键提交启动器
rem  实际逻辑在 一键提交.ps1 中；本文件只负责调用 PowerShell。
rem  双击运行，或带提交说明运行：一键提交.bat "修复某个问题"
rem ============================================================

set "PS1=%~dp0一键提交.ps1"
if not exist "%PS1%" (
    echo [错误] 找不到 一键提交.ps1。
    pause
    exit /b 1
)

where pwsh >nul 2>nul
if not errorlevel 1 (
    pwsh -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
) else (
    powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
)

set "CODE=%ERRORLEVEL%"
echo.
pause
exit /b %CODE%
