@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "$dest = Join-Path $env:USERPROFILE 'Documents\cifraHoliness'; if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest | Out-Null; git clone https://github.com/RafaelGarciaRodrigues/cifraHoliness $dest }; Set-Location $dest; git pull"
pause
