@echo off
title Instalador Git silencioso - by Grok

:: ====================== VERIFICAÇÃO DE ADMINISTRADOR ======================
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERRO] Este script precisa ser executado como ADMINISTRADOR.
    echo Clique direito no arquivo .bat ^> "Executar como administrador".
    pause
    exit /b 1
)

:: ====================== VERIFICA SE GIT JÁ ESTÁ INSTALADO ======================
where git >nul 2>&1
if %errorlevel% == 0 (
    echo.
    echo Git ja esta instalado!
    git --version
    pause
    exit /b 0
)

echo.
echo Baixando a versao mais recente do Git (64-bit)...

:: ====================== DOWNLOAD AUTOMÁTICO ======================
powershell -NoProfile -Command "$ProgressPreference = 'SilentlyContinue'; $latest = Invoke-RestMethod -Uri 'https://api.github.com/repos/git-for-windows/git/releases/latest'; $asset = $latest.assets | Where-Object { $_.name -like 'Git-*-64-bit.exe' }; Invoke-WebRequest -Uri $asset.browser_download_url -OutFile 'GitInstaller.exe'"

if not exist "GitInstaller.exe" (
    echo.
    echo [ERRO] Falha ao baixar o instalador. Verifique sua internet.
    pause
    exit /b 1
)

echo Criando configuracao silenciosa...

:: ====================== ARQUIVO DE CONFIGURAÇÃO (força PATH no CMD) ======================
(
echo [Setup]
echo Lang=default
echo Dir=C:\Program Files\Git
echo Group=Git
echo NoIcons=0
echo SetupType=default
echo Components=icons,ext\reg\shellhere,assoc,assoc_sh
echo Tasks=
echo PathOption=Cmd
) > git_options.ini

echo Instalando Git silenciosamente (pode demorar 30-60 segundos)...

:: ====================== INSTALAÇÃO SILENCIOSA ======================
start /wait GitInstaller.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /LOADINF=git_options.ini

echo.
echo Limpando arquivos temporarios...
del /f /q GitInstaller.exe git_options.ini

echo.
echo ================================================
echo   INSTALACAO CONCLUIDA COM SUCESSO!
echo ================================================
echo.
echo Agora abra um NOVO Prompt de Comando e digite:
echo git --version
echo.
pause