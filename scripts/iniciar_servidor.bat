@echo off
REM Inicia o Extratus (site) sempre a partir da pasta certa do projeto,
REM independente de onde esse atalho for chamado.

cd /d "%~dp0.."
call .venv\Scripts\activate
python -m uvicorn app.web.main:app --host 0.0.0.0 --port 8000

pause
