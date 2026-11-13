@echo off
chcp 65001 >nul

echo ===================================
echo 清理 pdfreader 项目...
echo ===================================
cd /d "c:\Projects\pdfreader"
rd /s /q "build" >nul 2>&1
rd /s /q "dist" >nul 2>&1
echo.
echo pdfreader 清理完成！
echo.
