@echo off
chcp 936 >nul
cd /d "%~dp0"
echo ============================================
echo   Ave 打包 (免装 Python 和 Node 的 exe)
echo ============================================
echo.

if not exist "ffmpeg.exe" (
  echo [错误] 缺 ffmpeg.exe。需要 GPL full build 含 libx264。
  echo        跑 python 准备素材.py 自动下载
  pause & exit /b 1
)
if not exist "fonts\SourceHanSansSC-Bold.otf" (
  echo [错误] 缺 fonts\SourceHanSansSC-Bold.otf 默认字幕字体。
  echo        跑 python 准备素材.py 自动下载
  pause & exit /b 1
)
if not exist "licenses\ffmpeg\SOURCE-OFFER.md" (
  echo [错误] 缺 licenses\ 许可声明。随包 ffmpeg 是 GPL 构建，
  echo        对外分发必须附许可与源码获取说明，不能少这个目录。
  pause & exit /b 1
)

echo [1/6] 检查随包素材...
python 准备素材.py --check || (echo [错误] 素材检查未通过 & pause & exit /b 1)

echo [2/6] 构建前端...
cd frontend
call npm run build || (echo [错误] 前端构建失败 & cd .. & pause & exit /b 1)
cd ..

echo [3/6] 复制前端产物到 web\...
if exist "web" rd /s /q "web"
xcopy /e /i /q "frontend\dist" "web\" >nul || (echo [错误] 复制失败 & pause & exit /b 1)
rem 许可声明也拷进 web，界面页脚的「开源许可」链接指向这里
xcopy /e /i /q "licenses" "web\licenses\" >nul || (echo [错误] 复制许可失败 & pause & exit /b 1)

echo [4/6] 复制凭证到包内 (内部使用)...
rem 用户 2026-08-27 定：内部使用，凭证打进 exe，免得每台机器手配一遍。
rem 明文，拿到 dist\Ave 的人都能提取出 token —— 对外分发前必须去掉这一步。
rem 打包完会删掉，不让明文凭证长期躺在仓库目录里。
set "CRED=%LOCALAPPDATA%\Ave\credentials.json"
if exist "%CRED%" copy /y "%CRED%" "_bundled_credentials.json" >nul
if exist "_bundled_credentials.json" (echo         已打入凭证，仅限内部分发) else (echo         无凭证，走每台机器一份用户数据目录)

echo [5/6] PyInstaller 打包 (约 3-8 分钟)...
python -m PyInstaller --noconfirm --clean Ave.spec || (echo [错误] 打包失败 & pause & exit /b 1)

rem 清掉刚拷进来的明文凭证 —— 它已经在 exe 里了，仓库目录不留副本
if exist "_bundled_credentials.json" del /q "_bundled_credentials.json"

rem 使用说明放 exe 同级，不走 spec 的 datas ——
rem datas 会落进 _internal 目录里，同事翻不到。解压第一眼就该看见它。
if exist "docs\使用说明.md" (
  copy /y "docs\使用说明.md" "dist\Ave\使用说明.md" >nul
  echo         已放入 使用说明.md
) else (
  echo [警告] 缺 docs\使用说明.md，同事拿到包没有操作手册
)

echo [6/6] 打 zip 压缩包...
rem Compress-Archive 是 Windows 自带的，不额外装 7-zip。
rem 压 dist\Ave\* 而不是 dist\Ave 本身 ——
rem 前者解压出来直接是文件，后者会多套一层目录。
rem _internal 里有 ffmpeg / 字体 / 前端页面，一个都不能少。
if exist "Ave-分发.zip" del /q "Ave-分发.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Ave\*' -DestinationPath 'Ave-分发.zip' -CompressionLevel Optimal" || (echo [错误] 压缩失败 & pause & exit /b 1)

echo.
echo ============================================
echo   完成: Ave-分发.zip
echo ============================================
for %%F in ("Ave-分发.zip") do echo 压缩包大小: %%~zF 字节
echo 把 Ave-分发.zip 发给同事，解压后双击 Ave.exe，同目录有 使用说明.md。
echo 首次运行会下载语音模型约 1.5G 到 %%LOCALAPPDATA%%\Ave
echo.
echo [重要] 这个 zip 里有明文凭证 (ARK Key / 火山 token)，解压就能提取。
echo        只发内部同事，别放公开网盘或任何对外渠道。
echo.
echo 对外分发前请先读 licenses\ffmpeg\SOURCE-OFFER.md，
echo 把里面的 ^<待填^> 补齐 (源码归档地址)。
pause
