@echo off
cd /d "%~dp0"
set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=pythonw"
for %%F in ("%~dp0*.py") do start "" "%PYTHONW%" "%%~fF"