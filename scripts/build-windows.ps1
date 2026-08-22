# Build the copy-and-run Windows distribution (CLI plus Podle-themed GUI).
[CmdletBinding()]
param(
    [string]$Python = "py -3.11",
    [switch]$SkipInstaller
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
    & $pythonExe -m PyInstaller --noconfirm --clean --distpath dist --workpath build\windows-cli pps.spec
    & $pythonExe -m PyInstaller --noconfirm --clean --distpath dist --workpath build\windows-gui pps-gui.spec
    & $pythonExe -m PyInstaller --noconfirm --clean --distpath dist --workpath build\windows-installed-gui PodleSkewl.spec

    $release = Join-Path $root "dist\PodleParsesSkewl-Windows"
    if (Test-Path $release) { Remove-Item -Recurse -Force $release }
    New-Item -ItemType Directory -Path $release | Out-Null
    Copy-Item (Join-Path $root "dist\pps.exe") $release
    Copy-Item (Join-Path $root "dist\pps-gui.exe") $release
    # The copy-ready folder keeps the historical GUI name. The installer uses
    # the separately built, user-facing PodleSkewl.exe.
    Copy-Item (Join-Path $root "dist\PodleSkewl.exe") $release
    Copy-Item (Join-Path $root "README.md") $release
    Copy-Item (Join-Path $root "WINDOWS-SMOKE-TEST.md") $release
    $zip = Join-Path $root "dist\PodleParsesSkewl-Windows.zip"
    if (Test-Path $zip) { Remove-Item -Force $zip }
    Compress-Archive -Path (Join-Path $release "*") -DestinationPath $zip

    Write-Host "Built $release"
    Write-Host "Smoke test: .\dist\PodleParsesSkewl-Windows\pps.exe --version"
    & (Join-Path $release "pps.exe") --version
    Write-Host "ZIP: $zip"

    if (-not $SkipInstaller) {
        $iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if (-not $iscc) {
            throw "ISCC.exe was not found. Install Inno Setup 6, add its directory to PATH, or rerun with -SkipInstaller."
        }
        & $iscc.Source "/DAppVersion=0.1.0" (Join-Path $root "installer\PodleSkewl.iss")
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }
        Write-Host "Installer: $(Join-Path $root 'dist\PodleSkewl-Setup.exe')"
    }
} finally {
    Pop-Location
}
