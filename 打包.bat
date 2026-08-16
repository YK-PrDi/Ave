@echo off
chcp 936 >nul
cd /d "%~dp0"
echo ============================================
echo   Ave 打包 (免装 Python 和 Node 的 exe)
echo ============================================
echo.

if not exist "ffmpeg.exe" (
  echo [错误] 缺 ffmpeg.exe。需要 GPL full build 含 libx264。
  echo        获取方式见 docs\进度与待办.md 落地 4
  pause & exit /b 1
)
if not exist "fonts\新青年体.ttf" (
  echo [错误] 缺 fonts\新青年体.ttf
  pause & exit /b 1
)

echo [1/3] 构建前端...
cd frontend
call npm run build || (echo [错误] 前端构建失败 & cd .. & pause & exit /b 1)
cd ..

echo [2/3] 复制前端产物到 web\...
if exist "web" rd /s /q "web"
xcopy /e /i /q "frontend\dist" "web\" >nul || (echo [错误] 复制失败 & pause & exit /b 1)

echo [3/3] PyInstaller 打包 (约 3-8 分钟)...
python -m PyInstaller --noconfirm --clean Ave.spec || (echo [错误] 打包失败 & pause & exit /b 1)

echo.
echo ============================================
echo   完成: dist\Ave\Ave.exe
echo ============================================
echo 分发时整个 dist\Ave 文件夹一起拷走。
echo 首次运行会下载语音模型约 1.5G 到 %%LOCALAPPDATA%%\Aveecho.
pause
