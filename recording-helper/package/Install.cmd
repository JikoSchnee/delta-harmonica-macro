@echo off
setlocal
set "APP_PATH=%~dp0HarmonicaRecorder.exe"

if not exist "%APP_PATH%" (
  echo HarmonicaRecorder.exe was not found next to this installer.
  pause
  exit /b 1
)

echo Registering helper protocol for this Windows user...
powershell -NoProfile -Command "$ErrorActionPreference='Stop'; try { $key=[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Software\Classes\harmonica-recorder'); $key.SetValue('', 'URL:Harmonica Recorder Protocol', [Microsoft.Win32.RegistryValueKind]::String); $key.SetValue('URL Protocol', '', [Microsoft.Win32.RegistryValueKind]::String); $command=$key.CreateSubKey('shell\open\command'); $value=([char]34).ToString()+$env:APP_PATH+([char]34)+' '+([char]34)+([char]37)+'1'+([char]34); $command.SetValue('', $value, [Microsoft.Win32.RegistryValueKind]::String); if ($command.GetValue('') -ne $value) { throw 'Protocol command verification failed.' }; Write-Output ('Registered command: '+$value); $command.Close(); $key.Close() } catch { Write-Output ('ERROR: '+$_.Exception.Message); exit 1 }"
set "REGISTER_EXIT=%errorlevel%"
if not "%REGISTER_EXIT%"=="0" (
  echo PowerShell exit code: %REGISTER_EXIT%
  goto failed
)

echo Protocol registered for this Windows user:
reg query "HKCU\Software\Classes\harmonica-recorder\shell\open\command" /ve
if errorlevel 1 goto failed
echo Installation complete. You can now use "Export to Macro Recording Helper" on the website.
pause
exit /b 0

:failed
echo Protocol registration failed. Please keep this window open and report the error above.
pause
exit /b 1
