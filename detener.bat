@echo off
rem Baja el servidor del Aplicador sin tocar otros Python que puedas tener corriendo:
rem busca el proceso cuya linea de comando apunta a servidor.py de esta carpeta.
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$mios = Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe'\" | Where-Object { $_.CommandLine -like '*servidor.py*' };" ^
  "if (-not $mios) { 'El servidor no estaba corriendo.'; exit }" ^
  "$mios | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; \"Detenido el proceso $($_.ProcessId).\" }"

echo.
pause
