@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-Location '%~dp0'; git add -A; $msg = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'; git commit -m $msg; git push"
pause
