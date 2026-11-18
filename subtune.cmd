@echo off
rem Runs htTamer with its private Python environment.
pushd "%~dp0"
"%LOCALAPPDATA%\subtune-venv\Scripts\python.exe" -m subtune %*
set rc=%ERRORLEVEL%
popd
exit /b %rc%
