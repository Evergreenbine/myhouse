@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   华阳多媒体 - 加班工资查询工具
echo ========================================
echo.
echo 检查依赖...
py -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
echo.
echo 启动应用...
py main.py
pause
