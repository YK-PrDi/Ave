@echo off
chcp 936 >nul
title 分镜自动化混剪
cd /d "%~dp0"

echo ============================================
echo   分镜自动化混剪
echo ============================================
echo.

REM ---- 检查 Python ----
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 找不到 Python。
    echo.
    echo 请先安装 Python 3.10 以上版本，安装时勾选
    echo "Add Python to PATH"，装完重新双击本文件。
    echo 下载地址 https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

REM ---- 检查 Python 依赖 ----
python -c "import fastapi, uvicorn, faster_whisper, PIL" >nul 2>&1
if errorlevel 1 (
    echo [提示] 缺少依赖，现在自动安装，约 2-5 分钟，只需一次
    echo.
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [错误] 依赖安装失败。若是网络慢，试着换国内镜像：
        echo   python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
        echo.
        pause
        exit /b 1
    )
    echo.
)

REM ---- 检查语音识别模型 ----
if exist "models\fw_medium\model.bin" goto modelok
if exist "models\fw_small\model.bin" goto modelok
echo [提示] 缺少语音识别模型，现在下载，约 1.5G，只需一次
echo        走国内镜像。若中断，重新双击本文件会自动续传
echo.
python 下载模型.py
if errorlevel 1 (
    echo.
    echo [错误] 模型下载失败，请检查网络后重试。
    pause
    exit /b 1
)
echo.
:modelok

REM ---- 释放被占用的端口 ----
REM 上次没正常退出时端口会留着，不清掉新进程起不来
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8756" ^| findstr "LISTENING"') do (
    echo [提示] 端口 8756 被占用，正在清理
    taskkill /F /PID %%p >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do (
    echo [提示] 端口 5173 被占用，正在清理
    taskkill /F /PID %%p >nul 2>&1
)

REM ---- 起后端 ----
echo [1/2] 启动后端服务
start "混剪-后端" /min cmd /c "python -m ave.server"

REM 等后端就绪再起前端，否则界面首次加载会报连不上
python 等待就绪.py http://127.0.0.1:8756/api/health 40
if errorlevel 1 (
    echo.
    echo [错误] 后端启动超时。
    echo        请看任务栏那个"混剪-后端"窗口里的报错信息。
    pause
    exit /b 1
)
echo       后端就绪

REM ---- 装界面依赖 ----
if exist "frontend\node_modules" goto frontready

node --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [错误] 找不到 Node.js，界面需要它。
    echo        下载地址 https://nodejs.org/  装 LTS 版本即可
    echo.
    pause
    exit /b 1
)

echo       首次运行，安装界面依赖，约 1-3 分钟，只需一次
pushd frontend
call npm install
if errorlevel 1 (
    echo.
    echo [错误] 界面依赖安装失败，请检查网络。
    popd
    pause
    exit /b 1
)
popd
:frontready

REM ---- 起前端 ----
echo [2/2] 启动界面
pushd frontend
start "混剪-界面" /min cmd /c "npm run dev"
popd

REM 等 vite 就绪再开浏览器，否则会打开一个白页
python 等待就绪.py http://127.0.0.1:5173/ 60
if errorlevel 1 (
    echo.
    echo [错误] 界面启动超时。
    echo        请看任务栏那个"混剪-界面"窗口里的报错信息。
    pause
    exit /b 1
)
echo       界面就绪
echo.

start "" http://localhost:5173/

echo ============================================
echo   已在浏览器打开。若没自动弹出，手动访问
echo   http://localhost:5173/
echo.
echo   用完请双击"停止.bat"，或直接关掉任务栏那
echo   两个窗口（混剪-后端、混剪-界面）
echo ============================================
echo.
pause
