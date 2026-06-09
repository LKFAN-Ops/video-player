@echo off
rem 直接启动electron应用程序，绕过PowerShell执行策略限制

rem 设置模型缓存目录为当前目录下的models_cache
set HF_HOME=%~dp0models_cache

rem 创建模型缓存目录（如果不存在）
if not exist "%HF_HOME%" mkdir "%HF_HOME%"

echo 正在启动视频播放器应用...
echo 模型缓存目录: %HF_HOME%

echo 正在检查node_modules\electron\dist\electron.exe...
if exist "node_modules\electron\dist\electron.exe" (
    echo 找到electron.exe，正在启动...
    "node_modules\electron\dist\electron.exe" .
) else if exist "node_modules\.bin\electron.cmd" (
    echo 找到electron.cmd，正在启动...
    "node_modules\.bin\electron.cmd" .
) else (
    echo 未找到electron可执行文件，请先运行npm install
    pause
)

pause