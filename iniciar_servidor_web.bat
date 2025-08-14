@echo off
setlocal EnableExtensions EnableDelayedExpansion

:: ===== Console =====
chcp 1252 > nul
title WebServer Local - Servidor Python
color 0A
cls

:: ===== Parâmetros =====
set "PORTA=8082"
set "DIRETORIO=C:\temp\webserverpython"
set "SERVIDOR_PY=web_server_enhanced.py"
set "INDEX_ORIG=index 2.html"
set "INDEX_DEST=index.html"

echo WebServer Local - Servidor Python
echo ==================================
echo.

:: Python
where python > nul 2>&1 || (
  echo [ERRO] Python não encontrado. Instale em https://www.python.org/downloads/
  pause
  exit /b 1
)
for /f "tokens=2" %%V in ('python --version 2^>^&1') do set "PYTHON_VERSION=%%V"
echo [INFO] Python %PYTHON_VERSION%
echo.

:: Diretório
if not exist "%DIRETORIO%" (
  echo [ERRO] O diretório "%DIRETORIO%" não existe.
  set /p CRIAR_DIR="Deseja criar? (S/N): "
  if /i "!CRIAR_DIR!"=="S" (
    mkdir "%DIRETORIO%" 2> nul || (echo [ERRO] Falha ao criar. & pause & exit /b 1)
    echo [INFO] Diretório criado.
  ) else exit /b 0
)

echo [INFO] Indo para: %DIRETORIO%
cd /d "%DIRETORIO%" 2> nul || (echo [ERRO] Sem acesso. & pause & exit /b 1)

:: Garante servidor (copia da pasta do .bat se faltando)
if not exist "%SERVIDOR_PY%" (
  echo [INFO] Copiando %SERVIDOR_PY%...
  copy "%~dp0%SERVIDOR_PY%" ".\" > nul || (echo [ERRO] Copia falhou. & pause & exit /b 1)
)

:: (Opcional) Copia/renomeia index 2.html como index.html se não existir
if not exist "%INDEX_DEST%" (
  if exist "%~dp0%INDEX_ORIG%" (
    echo [INFO] Copiando "%INDEX_ORIG%" como "%INDEX_DEST%"...
    copy "%~dp0%INDEX_ORIG%" ".\%INDEX_DEST%" > nul
  ) else (
    echo [AVISO] "%INDEX_DEST%" não existe e "%INDEX_ORIG%" não foi encontrado ao lado do .bat.
  )
)

:: Porta
netstat -an | find ":%PORTA% " | find "LISTENING" > nul
if not errorlevel 1 (
  echo [AVISO] Porta %PORTA% em uso.
  set /p NOVA_PORTA="Outra porta (ex.: 8085): "
  if defined NOVA_PORTA set "PORTA=%NOVA_PORTA%"
)

:: IP local
for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr "IPv4"') do (
  for /f "tokens=* delims= " %%B in ("%%A") do (set "LOCAL_IP=%%B" & goto :ipok)
)
:ipok
if not defined LOCAL_IP set "LOCAL_IP=127.0.0.1"

echo [INFO] IP local: %LOCAL_IP%
echo [INFO] Itens nesta pasta:
dir /b | find /c /v ""
echo.

echo [INFO] Iniciando servidor na porta %PORTA%...
echo - Local: http://localhost:%PORTA%
echo - Rede : http://%LOCAL_IP%:%PORTA%
echo.

start "" "http://localhost:%PORTA%/"
python "%SERVIDOR_PY%" "%DIRETORIO%" %PORTA%

echo.
echo [INFO] Servidor encerrado.
pause
exit /b 0
