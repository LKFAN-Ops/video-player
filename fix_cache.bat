@echo off
REM 修复Electron应用程序的缓存访问权限问题

REM 设置Electron应用程序的用户数据目录
set USER_DATA_DIR=%APPDATA%\bofangqi

REM 创建用户数据目录
if not exist "%USER_DATA_DIR%" (
    mkdir "%USER_DATA_DIR%"
    echo 创建用户数据目录成功: %USER_DATA_DIR%
) else (
    echo 用户数据目录已存在: %USER_DATA_DIR%
)

REM 设置环境变量，让Electron使用这个目录
set ELECTRON_USER_DATA_DIR=%USER_DATA_DIR%

REM 运行Electron应用程序
echo 正在启动应用程序...
start "bofangqi" "node_modules\electron\dist\electron.exe" .

pause