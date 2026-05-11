# -*- mode: python ; coding: utf-8 -*-
import sys
sys.path.insert(0, '.')
from version import VERSION

block_cipher = None

a = Analysis(
    ['tts_app.py'],
    pathex=[],
    binaries=[],
    datas=[('build/icon.icns', '.')],
    hiddenimports=[
        'PyQt6.sip', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
        'PyQt6.QtMultimedia', 'PyQt6.QtNetwork',
        'app_constants', 'app_utils', 'app_workers', 'app_dialogs',
        'voice_library', 'settings_dialog', 'main_window', 'version',
        'telegram_config', 'certifi',
        'auto_video_workers',
        'anthropic', 'bs4', 'beautifulsoup4',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if sys.platform == 'darwin':
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='HedraStudio',
        debug=False,
        strip=False,
        upx=False,
        console=False,
        windowed=True,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        name='HedraStudio',
    )
    app = BUNDLE(
        coll,
        name='Hedra Studio.app',
        bundle_identifier='com.hedracentral.hedrastudio',
        icon='build/icon.icns',
        info_plist={
            'CFBundleShortVersionString': VERSION,
            'CFBundleVersion': VERSION,
            'NSHighResolutionCapable': True,
            'LSUIElement': False,
        },
    )

else:
    # Windows — single .exe
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='Hedra Studio',
        debug=False,
        strip=False,
        upx=False,
        console=False,
        windowed=True,
    )
