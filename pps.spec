# PyInstaller build definition for the console CLI.
# Build this on Windows with scripts/build-windows.ps1; PyInstaller does not
# cross-compile Windows executables from Linux or macOS.
from pathlib import Path

project_root = Path(SPEC).parent

analysis = Analysis(
    [str(project_root / "podleparsesskewl" / "__main__.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="pps",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
