@echo off
REM Inicia o Extratus (site) sempre a partir da pasta principal do projeto.
REM Antes de subir, chama o vigia (servidor_watchdog.ps1) que verifica se
REM ja existe um Extratus rodando neste computador - evita duas copias
REM brigando pela mesma porta, uma delas com codigo antigo escondido.

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0servidor_watchdog.ps1"

pause
