@echo off
title Abrir HTML em duas telas - Auto Detect
chcp 65001 >nul

:: ==================== CONFIGURAÇÃO ====================
:: Mude aqui se quiser usar Edge:
set "BROWSER=C:\Program Files\Google\Chrome\Application\chrome.exe"
:: set "BROWSER=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

:: Arquivos HTML (mesmo local do .bat)
set "HTML1=%~dp0app.html"
set "HTML2=%~dp0tela.html"
:: =====================================================

echo.
echo Verificando arquivos e navegador...

if not exist "%HTML1%" (
    echo ERRO: Nao encontrei "%HTML1%"
    pause
    exit /b
)
if not exist "%HTML2%" (
    echo ERRO: Nao encontrei "%HTML2%"
    pause
    exit /b
)
if not exist "%BROWSER%" (
    echo ERRO: Navegador nao encontrado em:
    echo    %BROWSER%
    pause
    exit /b
)

echo Arquivos e navegador OK.
echo Detectando monitores automaticamente...

:: === Cria o script PowerShell (sem caracteres especiais) ===
set "PS_SCRIPT=%TEMP%\abrir_duas_telas.ps1"

> "%PS_SCRIPT%" echo Add-Type -AssemblyName System.Windows.Forms;
>> "%PS_SCRIPT%" echo $screens = [System.Windows.Forms.Screen]::AllScreens;
>> "%PS_SCRIPT%" echo.
>> "%PS_SCRIPT%" echo if ($screens.Length -lt 2) {
>> "%PS_SCRIPT%" echo     Write-Host "Apenas UM monitor detectado!" -ForegroundColor Yellow;
>> "%PS_SCRIPT%" echo     $primary = $screens[0];
>> "%PS_SCRIPT%" echo     $secondary = $primary;
>> "%PS_SCRIPT%" echo } else {
>> "%PS_SCRIPT%" echo     $primary   = $screens ^| Where-Object { $_.Primary } ^| Select-Object -First 1;
>> "%PS_SCRIPT%" echo     $secondary = $screens ^| Where-Object { -not $_.Primary } ^| Select-Object -First 1;
>> "%PS_SCRIPT%" echo     Write-Host "Dois monitores detectados!" -ForegroundColor Green;
>> "%PS_SCRIPT%" echo }
>> "%PS_SCRIPT%" echo.
>> "%PS_SCRIPT%" echo $pX = $primary.WorkingArea.X;    $pY = $primary.WorkingArea.Y;
>> "%PS_SCRIPT%" echo $pW = $primary.WorkingArea.Width; $pH = $primary.WorkingArea.Height;
>> "%PS_SCRIPT%" echo $sX = $secondary.WorkingArea.X;    $sY = $secondary.WorkingArea.Y;
>> "%PS_SCRIPT%" echo $sW = $secondary.WorkingArea.Width; $sH = $secondary.WorkingArea.Height;
>> "%PS_SCRIPT%" echo.
>> "%PS_SCRIPT%" echo Write-Host "Tela Principal   -> X=$pX  Y=$pY  Tamanho=${pW}x${pH}" -ForegroundColor White;
>> "%PS_SCRIPT%" echo Write-Host "Tela Secundaria  -> X=$sX  Y=$sY  Tamanho=${sW}x${sH}" -ForegroundColor White;
>> "%PS_SCRIPT%" echo.
>> "%PS_SCRIPT%" echo $html1 = '%HTML1%'.Replace('\','/');
>> "%PS_SCRIPT%" echo $html2 = '%HTML2%'.Replace('\','/');
>> "%PS_SCRIPT%" echo $chrome = """%BROWSER%""";
>> "%PS_SCRIPT%" echo.
>> "%PS_SCRIPT%" echo Write-Host "Abrindo app.html na tela principal..." -ForegroundColor Cyan;
>> "%PS_SCRIPT%" echo Start-Process $chrome -ArgumentList '--new-window', '--user-data-dir=%TEMP%\chrome_monitor1', "file:///$html1", "--window-position=$pX,$pY", "--window-size=$pW,$pH";
>> "%PS_SCRIPT%" echo Start-Sleep -Milliseconds 1500;
>> "%PS_SCRIPT%" echo.
>> "%PS_SCRIPT%" echo Write-Host "Abrindo tela.html na tela secundaria..." -ForegroundColor Cyan;
>> "%PS_SCRIPT%" echo Start-Process $chrome -ArgumentList '--new-window', '--user-data-dir=%TEMP%\chrome_monitor2', "file:///$html2", "--window-position=$sX,$sY", "--window-size=$sW,$sH";
>> "%PS_SCRIPT%" echo.
>> "%PS_SCRIPT%" echo Write-Host "Tudo aberto com sucesso!" -ForegroundColor Green;

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"

del "%PS_SCRIPT%" 2>nul

echo.
echo Pronto! Verifique as coordenadas acima.
pause