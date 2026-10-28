@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if "%~1"=="" (
  echo Usage: host.cmd ^<file^>
  pause
  exit /b 1
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 "%~dp0host_file.py" "%~1"
  set ERR=%ERRORLEVEL%
  goto :done
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python "%~dp0host_file.py" "%~1"
  set ERR=%ERRORLEVEL%
  goto :done
)

echo Python was not found on PATH. Install Python 3 and try again.
set ERR=1

:done
echo.
pause
exit /b %ERR%
