# Hace que el servidor arranque solo al iniciar sesion en Windows, sin ventana de consola.
# Se corre una sola vez. Para deshacerlo: borrar el acceso directo que crea, o pasarle -Quitar.
#
#   powershell -ExecutionPolicy Bypass -File instalar-inicio.ps1
#   powershell -ExecutionPolicy Bypass -File instalar-inicio.ps1 -Quitar

param([switch]$Quitar)

$ErrorActionPreference = "Stop"

$carpeta = Split-Path -Parent $MyInvocation.MyCommand.Path
$inicio  = [Environment]::GetFolderPath("Startup")
$atajo   = Join-Path $inicio "Aplicador.lnk"

if ($Quitar) {
    if (Test-Path $atajo) {
        Remove-Item $atajo -Force
        "Listo: el Aplicador ya no arranca con Windows."
    } else {
        "No estaba instalado, no hay nada que quitar."
    }
    return
}

# pythonw.exe es python sin consola. Va al lado del python.exe que este en el PATH.
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "No encuentro python en el PATH." }

$pythonw = Join-Path (Split-Path -Parent $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "No encuentro pythonw.exe junto a $python" }

$servidor = Join-Path $carpeta "servidor.py"
if (-not (Test-Path $servidor)) { throw "No encuentro servidor.py en $carpeta" }

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($atajo)
$lnk.TargetPath       = $pythonw
$lnk.Arguments        = "`"$servidor`""
$lnk.WorkingDirectory = $carpeta
$lnk.Description      = "Servidor local del Aplicador"
$lnk.WindowStyle      = 7   # minimizado; con pythonw igual no hay ventana
$lnk.Save()

""
"Instalado: $atajo"
"  lanza:   $pythonw `"$servidor`""
""
"Arranca solo la proxima vez que inicies sesion. Para levantarlo ahora sin reiniciar:"
"  Start-Process -WindowStyle Hidden `"$pythonw`" -ArgumentList `"$servidor`""
""
"El panel queda en  http://127.0.0.1:8765/historial"
"Como no hay consola, lo que pase se escribe en  servidor.log"
"Para apagarlo:  detener.bat"
