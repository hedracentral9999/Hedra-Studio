# -*- mode: python ; coding: utf-8 -*-
import sys
import shutil
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files
sys.path.insert(0, '.')
from version import VERSION

block_cipher = None

datas = [
    ('assets/sf-symbols', 'assets/sf-symbols'),
    ('assets/fonts', 'assets/fonts'),
    ('luts', 'luts'),
    ('knowledge/one-shot', 'knowledge/one-shot'),
    ('docs/tts', 'docs/tts'),
]
datas += collect_data_files('faster_whisper')

binaries = []
for tool in ('ffmpeg', 'ffprobe'):
    found = shutil.which(tool)
    if found:
        binaries.append((found, 'bin'))

for src in ('build/icon.icns', 'build/icon.ico'):
    if Path(src).exists():
        datas.append((src, '.'))

win_icon = 'build/icon.ico' if Path('build/icon.ico').exists() else None

a = Analysis(
    ['tts_app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'PyQt6.sip', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
        'PyQt6.QtMultimedia', 'PyQt6.QtNetwork',
        'app_constants', 'app_icons', 'app_utils', 'app_workers', 'app_dialogs',
        'voice_library', 'settings_dialog', 'main_window', 'prompt_files', 'version',
        'oneshot_engine', 'oneshot_engine.contracts', 'oneshot_engine.render_gate',
        'certifi',
        'auto_video_workers',
        'faster_whisper', 'ctranslate2', 'tokenizers', 'av', 'onnxruntime', 'numpy',
        'anthropic', 'bs4',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['telegram_config', 'tkinter', 'matplotlib', 'scipy'],
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
        icon=win_icon,
        debug=False,
        strip=False,
        upx=False,
        console=False,
        windowed=True,
    )
