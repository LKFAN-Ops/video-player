@echo off
rem 简单启动脚本
setlocal

rem 设置模型缓存目录
set HF_HOME=%~dp0models_cache
if not exist "%HF_HOME%" mkdir "%HF_HOME%"

echo 模型缓存目录: %HF_HOME%
echo 启动Electron应用...

rem 直接调用electron.exe
"node_modules\electron\dist\electron.exe" .

endlocal