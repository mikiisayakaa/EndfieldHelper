# PyInstaller spec file for Endfield Helper

import sys
import os

project_root = SPECPATH

a = Analysis(
    [os.path.join(project_root, 'main.py')],
    pathex=[project_root],
    binaries=[],
    datas=[
        (os.path.join(project_root, 'configs'), 'configs'),
        (os.path.join(project_root, 'templates'), 'templates'),
        (os.path.join(project_root, 'imgs'), 'imgs'),
    ],
    hiddenimports=['cv2', 'easyocr', 'PIL', 'pynput', 'pyautogui', 'mouse', 'numpy', 'ahk'],
    hookspath=[],
    runtime_hooks=[],
    excludedimports=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Endfield Helper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join(project_root, 'imgs', 'icon.png'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Endfield Helper'
)
