@echo off
setlocal EnableExtensions
chcp 65001 >nul
title AutoScrcpy 依赖安装
cd /d "%~dp0"

echo ============================================================
echo  AutoScrcpy 依赖安装
echo ============================================================
echo.

echo [1/2] 安装 Python 依赖...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo [错误] Python 依赖安装失败。请确认已安装 Python 3.10+ 并加入 PATH。
  pause
  exit /b 1
)

echo.
echo [2/2] 安装 scrcpy（内含 adb）...
echo.
echo 说明：
echo   - Python 依赖从 PyPI 下载，scrcpy 由 winget 从 GitHub 下载安装包。
echo   - 如果下载超时或失败，请检查网络/代理是否能访问 GitHub；
echo     也可以手动下载后解压使用：
echo     https://github.com/Genymobile/scrcpy/releases
echo   - adb 随 scrcpy 一起提供，不需要单独安装。
echo   - scrcpy 5.0+ 才有 --hwdec 硬件解码，旧版本会由界面自动禁用该选项。
echo.

where winget >nul 2>nul
if errorlevel 1 (
  echo [提示] 没有找到 winget（应用安装程序）。
  echo 请从上面的 GitHub 地址下载 scrcpy-win64-v5.0.1.zip，
  echo 解压后把包含 scrcpy.exe 的目录加入 PATH。
  goto :done
)

winget install --id Genymobile.scrcpy -e --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
  echo.
  echo [提示] winget 安装没有成功，常见原因：
  echo   - 网络无法访问 GitHub，或代理没有生效；
  echo   - winget 源过旧，可先执行 winget source update 再重试；
  echo   - 已经安装过 scrcpy，可忽略此提示。
  echo 手动安装：https://github.com/Genymobile/scrcpy/releases
)

:done
echo.
echo 安装流程结束。可运行 start-debug.bat 检查 scrcpy 和 adb 是否在 PATH 中。
pause
