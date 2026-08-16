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
if not exist "licensesfmpeg\SOURCE-OFFER.md" (
  echo [错误] 缺 licenses\ 许可声明。随包 ffmpeg 是 GPL 构建，
  echo        对外分发必须附许可与源码获取说明，不能少这个目录。
  pause & exit /b 1
)

echo [1/4] 检查随包素材...
python 准备素材.py --check || (echo [错误] 素材检查未通过 & pause & exit /b 1)

echo [2/4] 构建前端...
cd frontend
call npm run build || (echo [错误] 前端构建失败 & cd .. & pause & exit /b 1)
cd ..

echo [3/4] 复制前端产物到 web\...
if exist "web" rd /s /q "web"
xcopy /e /i /q "frontend\dist" "web\" >nul || (echo [错误] 复制失败 & pause & exit /b 1)
rem 许可声明也拷进 web，界面页脚的「开源许可」链接指向这里
xcopy /e /i /q "licenses" "web\licenses\" >nul || (echo [错误] 复制许可失败 & pause & exit /b 1)

echo [4/4] PyInstaller 打包 (约 3-8 分钟)...
python -m PyInstaller --noconfirm --clean Ave.spec || (echo [错误] 打包失败 & pause & exit /b 1)

echo.
echo ============================================
echo   完成: dist\Ave\Ave.exe
echo ============================================
echo 分发时整个 dist\Ave 文件夹一起拷走。
echo 首次运行会下载语音模型约 1.5G 到 %%LOCALAPPDATA%%\Ave
echo.
echo 对外分发前请先读 licensesfmpeg\SOURCE-OFFER.md，
echo 把里面的 ^<待填^> 补齐 (源码归档地址)。
pause
