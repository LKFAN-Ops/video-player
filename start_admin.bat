@echo off
REM 以管理员身份运行Electron应用程序，解决缓存访问权限问题
powershell -Command "Start-Process 'node_modules\electron\dist\electron.exe' -ArgumentList '.' -Verb RunAs"
pause