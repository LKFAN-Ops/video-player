@echo off

rem 简单启动脚本
set HF_HOME=%~dp0models_cache

if not exist "%HF_HOME%" mkdir "%HF_HOME%"

echo Model cache: %HF_HOME%
echo Starting app...

node_modules\electron\dist\electron.exe .

pause