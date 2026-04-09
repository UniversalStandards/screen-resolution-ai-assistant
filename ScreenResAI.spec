# -*- mode: python ; coding: utf-8 -*-
# ScreenResAI.spec

block_cipher = None

from PyInstaller.utils.hooks import collect_all

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all('customtkinter')
anth_datas, anth_binaries, anth_hiddenimports = collect_all('anthropic')

all_datas    = ctk_datas + anth_datas
all_binaries = ctk_binaries + anth_binaries
all_hidden   = ctk_hiddenimports + anth_hiddenimports + [
    'tkinter', 'tkinter.messagebox', 'tkinter.filedialog',
    'ctypes', 'ctypes.wintypes', 'winreg', 'win32api', 'win32con',
    'anthropic', 'httpx', 'httpcore', 'certifi',
    'charset_normalizer', 'idna', 'sniffio', 'anyio', 'packaging',
]

a = Analysis(
    ['main.py'], pathex=['.'],
    binaries=all_binaries, datas=all_datas,
    hiddenimports=all_hidden,
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy'],
    cipher=block_cipher, noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='ScreenResAI',
    debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, upx_exclude=[],
    runtime_tmpdir=None, console=False,
    disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None,
    uac_admin=True,
    version='version_info.txt',
)
