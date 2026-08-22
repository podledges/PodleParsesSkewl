# PyInstaller definition for the Podle-themed Windows launcher.
from pathlib import Path

project_root = Path(SPEC).parent
analysis = Analysis(
    [str(project_root / "podleparsesskewl" / "gui.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[],
    hiddenimports=["tkinter", "tkinter.filedialog", "tkinter.messagebox", "tkinter.ttk"],
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
    name="pps-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
