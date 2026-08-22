# Build the standalone Windows CLI executable.
[CmdletBinding()]
param(
    [string]$Python = "py -3.11"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venv = Join-Path $root ".venv-windows-build"
$pythonExe = Join-Path $venv "Scripts\python.exe"

Push-Location $root
try {
    if (-not (Test-Path $pythonExe)) {
        Invoke-Expression "$Python -m venv `"$venv`""
    }
    & $pythonExe -m pip install --upgrade pip
    & $pythonExe -m pip install ".[build]"
    & $pythonExe -m PyInstaller --noconfirm --clean --distpath dist --workpath build\windows pps.spec
    Write-Host "Built $root\dist\pps.exe"
    Write-Host "Smoke test: .\dist\pps.exe --version"
    & (Join-Path $root "dist\pps.exe") --version
} finally {
    Pop-Location
}
