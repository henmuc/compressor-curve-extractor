@echo off
setlocal

cd /d "%~dp0"

set "CONDA_EXE="
for /f "delims=" %%i in ('where conda 2^>nul') do (
  set "CONDA_EXE=%%i"
  goto :found_conda
)

for %%i in ("%USERPROFILE%\anaconda3\Scripts\conda.exe" "%USERPROFILE%\miniconda3\Scripts\conda.exe" "C:\ProgramData\anaconda3\Scripts\conda.exe") do (
  if exist "%%~i" (
    set "CONDA_EXE=%%~i"
    goto :found_conda
  )
)

echo [error] conda.exe not found. Please install or repair Anaconda/Miniconda.
pause
exit /b 1

:found_conda
echo Using conda: %CONDA_EXE%
call "%CONDA_EXE%" run -n compressor python -m src.main
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo [error] Program exited with code %EXIT_CODE%.
  pause
  exit /b %EXIT_CODE%
)

endlocal
exit /b 0
