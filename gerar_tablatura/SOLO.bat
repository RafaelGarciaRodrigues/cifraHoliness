@echo off
rem Abre a Tela de Solos: sobe o servidor (python app.py) e abre o navegador.
rem A janela "Tela de Solos - servidor" precisa ficar aberta; fechar ela encerra a interface.
cd /d "%~dp0"
start "Tela de Solos - servidor" python app.py --sem-navegador

rem espera o servidor responder (até ~15 s) antes de abrir o navegador
for /l %%i in (1,1,30) do (
    powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 http://127.0.0.1:8765/api/musicas | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1 && goto abrir
    timeout /t 1 /nobreak >nul
)
:abrir
start "" http://127.0.0.1:8765
