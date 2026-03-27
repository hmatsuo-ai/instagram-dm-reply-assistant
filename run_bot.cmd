@echo off
cd /d "%~dp0"
python -m uvicorn bot_server.main:app --host 0.0.0.0 --port 8000
