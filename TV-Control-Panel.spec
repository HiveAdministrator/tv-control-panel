# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path(SPECPATH)
ADB_DIR = ROOT / 'android-platform-tools' / 'platform-tools'

a = Analysis(
    [str(ROOT / 'tv-panel.py')],
    pathex=[],
    binaries=[
        (str(ADB_DIR / 'adb.exe'), 'platform-tools'),
        (str(ADB_DIR / 'AdbWinApi.dll'), 'platform-tools'),
        (str(ADB_DIR / 'AdbWinUsbApi.dll'), 'platform-tools'),
    ],
    datas=[(str(ROOT / 'ico.png'), '.'), (str(ROOT / 'tv-panel.ico'), '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TV-Control-Panel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(ROOT / 'tv-panel.ico')],
)
