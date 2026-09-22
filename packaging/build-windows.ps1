#Requires -Version 5.1
<#
.SYNOPSIS
  Build the Tempo sidecar installer for Windows (Velopack).
.DESCRIPTION
  PyInstaller --onedir (Velopack requires a folder, NOT --onefile) then
  `vpk pack` into Setup.exe (+MSI with -Msi). Version defaults to
  service/pyproject.toml so there is exactly one version source.
  Docs: https://docs.velopack.io/getting-started/python
        https://docs.velopack.io/packaging/installer
  Prerequisites (release machine): Python 3.11+, pip install ./service,
  pip install pyinstaller, dotnet tool install -g vpk, code-signing cert.
.EXAMPLE
  .\packaging\build-windows.ps1
  .\packaging\build-windows.ps1 -Version 0.2.0 -Channel beta -Msi
#>
param(
  [string]$Version = "",
  [string]$Channel = "stable",
  [switch]$Msi
)
$ErrorActionPreference = "Stop"

$root = Split-Path $PSScriptRoot -Parent
if (-not $Version) {
  $toml = Get-Content (Join-Path $root "service\pyproject.toml") -Raw
  if ($toml -notmatch '(?m)^version\s*=\s*"([^"]+)"') { throw "version not found in pyproject.toml" }
  $Version = $Matches[1]
}
Write-Output "building TempoSidecar $Version ($Channel)"

Push-Location (Join-Path $root "service")
try {
  python -m PyInstaller --noconfirm --clean --onedir --name TempoSidecar `
    --paths . --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols.http.auto `
    tempo_service/app.py
} finally {
  Pop-Location
}
$publish = Join-Path $root "dist\TempoSidecar"
$vpk = @("pack", "--packId", "com.tempo.sidecar", "--packVersion", $Version,
  "--packDir", $publish, "--mainExe", "TempoSidecar.exe", "--channel", $Channel)
if ($Msi) { $vpk += "--msi" }
& vpk @vpk
Write-Output "installer ready in dist/"
