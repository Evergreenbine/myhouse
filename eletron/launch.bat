@echo off
cd /d D:\code\manbo

:: 关闭旧进程
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im electron.exe >nul 2>&1

:: 清理缓存
rmdir /s /q D:\code\overtime-app\__pycache__ >nul 2>&1

:: 隐藏启动 Python 后端
powershell -WindowStyle Hidden -Command "Start-Process python -ArgumentList 'D:\code\overtime-app\api_server.py' -WindowStyle Hidden"

:: 等待后端就绪
ping 127.0.0.1 -n 3 >nul

:: 启动 Electron
start "" /MIN npx electron .
exit

