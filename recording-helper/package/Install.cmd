@echo off
setlocal
set "APP_PATH=%~dp0HarmonicaRecorder.exe"

if not exist "%APP_PATH%" (
  echo HarmonicaRecorder.exe was not found next to this installer.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$key='HKCU:\Software\Classes\harmonica-recorder'; New-Item $key -Force | Out-Null; Set-ItemProperty $key '(Default)' 'URL:Harmonica Recorder Protocol'; New-ItemProperty $key 'URL Protocol' -Value '' -Force | Out-Null; New-Item ($key + '\shell\open\command') -Force | Out-Null; Set-ItemProperty ($key + '\shell\open\command') '(Default)' (([char]34) + $env:APP_PATH + ([char]34) + ' "%%1"')"

echo Installation complete. You can now use "Export to Independent Helper" on the website.
pause
