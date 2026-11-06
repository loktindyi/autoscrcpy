@echo off
setlocal EnableExtensions
chcp 65001 >nul
title AutoScrcpy 一键提交
cd /d "%~dp0"

rem ============================================================
rem  AutoScrcpy 一键提交脚本
rem  双击运行：暂存全部更改 -> 提交 -> 推送到 GitHub
rem  也可以带提交说明运行：一键提交.bat "修复某个问题"
rem ============================================================

where git >nul 2>nul
if errorlevel 1 (
    if exist "%ProgramFiles%\Git\cmd\git.exe" (
        set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
    ) else if exist "%LocalAppData%\Programs\Git\cmd\git.exe" (
        set "PATH=%LocalAppData%\Programs\Git\cmd;%PATH%"
    )
)

git --version >nul 2>nul
if errorlevel 1 (
    echo [错误] 没有找到 Git，请先安装 Git for Windows。
    goto :fail
)

git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
    echo [错误] 当前目录不是 Git 仓库：%CD%
    goto :fail
)

echo.
echo ============================================
echo   AutoScrcpy 一键提交
echo ============================================
echo.

echo [1/3] 暂存所有更改...
git add -A
if errorlevel 1 goto :fail

git diff --cached --quiet
if not errorlevel 1 (
    echo.
    echo 没有需要提交的更改，工作区是干净的。
    goto :done
)

echo.
echo 将要提交的文件：
git diff --cached --stat

set "MSG=%~1"
if not defined MSG (
    echo.
    set /p "MSG=请输入提交说明（直接回车自动生成）: "
)
if not defined MSG set "MSG=自动提交 %date% %time%"

echo.
echo [2/3] 提交...
git commit -m "%MSG%"
if errorlevel 1 goto :fail

set "BRANCH="
for /f "delims=" %%b in ('git symbolic-ref --short HEAD 2^>nul') do set "BRANCH=%%b"
if not defined BRANCH (
    echo [错误] 当前不在任何分支上，无法自动推送。
    goto :fail
)

echo.
echo [3/3] 推送到 origin/%BRANCH% ...
git push -u origin "%BRANCH%"
if not errorlevel 1 goto :success

echo.
echo 直接推送失败，尝试通过系统代理重试...
call :read_system_proxy
if not defined SYSPROXY (
    echo.
    echo [错误] 推送失败，且没有检测到可用的系统代理。
    echo 请检查网络，或确认远程仓库地址是否正确。
    goto :fail
)

echo 使用系统代理：%SYSPROXY%
git -c http.proxy="%SYSPROXY%" push -u origin "%BRANCH%"
if errorlevel 1 (
    echo.
    echo [错误] 通过代理推送仍然失败。
    echo 如果提示 rejected，请先执行 git pull --rebase 后再试。
    goto :fail
)

:success
echo.
echo ============================================
echo   提交并推送成功
echo ============================================
echo   仓库: https://github.com/loktindyi/autoscrcpy
echo.
goto :done

:read_system_proxy
rem 从 Windows 系统代理设置中读取地址，供 GitHub 连接失败时重试。
set "SYSPROXY="
set "PROXYENABLE="
for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable 2^>nul ^| findstr /i "ProxyEnable"') do set "PROXYENABLE=%%B"
if /i not "%PROXYENABLE%"=="0x1" exit /b 0
for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyServer 2^>nul ^| findstr /i "ProxyServer"') do set "SYSPROXY=%%B"
if not defined SYSPROXY exit /b 0
echo %SYSPROXY% | findstr /i "=" >nul
if not errorlevel 1 (
    rem 兼容 http=...;https=... 这种写法，取 http= 后面的地址。
    for /f "tokens=1,2 delims=;" %%A in ("%SYSPROXY%") do (
        for /f "tokens=2 delims==" %%C in ("%%A") do set "SYSPROXY=%%C"
    )
)
if not "%SYSPROXY:~0,7%"=="http://" if not "%SYSPROXY:~0,8%"=="https://" set "SYSPROXY=http://%SYSPROXY%"
exit /b 0

:fail
echo.
echo 操作未完成，请查看上面的错误信息。
echo.
pause
exit /b 1

:done
echo.
pause
exit /b 0
