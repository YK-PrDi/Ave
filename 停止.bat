@echo off
chcp 936 >nul
title 停止混剪工具
cd /d "%~dp0"

echo 正在停止
echo.

set FOUND=0

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8756" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
    echo   已停止后端服务
    set FOUND=1
)

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
    echo   已停止界面服务
    set FOUND=1
)

REM 关掉那两个最小化的命令行窗口
taskkill /F /FI "WINDOWTITLE eq 混剪-后端*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq 混剪-界面*" >nul 2>&1

if "%FOUND%"=="0" echo   没有正在运行的服务

echo.
echo 已全部停止，可以关掉这个窗口了。
pause
