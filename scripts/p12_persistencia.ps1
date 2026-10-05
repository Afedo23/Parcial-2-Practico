# P12 en Windows PowerShell. Código de salida 0 = éxito.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
docker compose up --build -d
function Reintentar([string[]]$cmd) {
  for ($i = 0; $i -lt 30; $i++) { & docker @cmd; if ($LASTEXITCODE -eq 0) { return }; Start-Sleep 3 }
  throw "Falló tras reintentos: $cmd"
}
Reintentar @("compose","exec","-T","app","python","-m","catalogo.cli","persistencia","crear")
docker compose restart
Reintentar @("compose","exec","-T","app","python","-m","catalogo.cli","persistencia","verificar")
Write-Host "P12 OK: el marcador sobrevivió al reinicio."
