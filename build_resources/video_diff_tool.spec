# PyInstaller Spec file for Video Diff Tool
#
# To build:
# pyinstaller video_diff_tool.spec

import sys
import os
from PyInstaller.utils.hooks import collect_all

# Analyze the project structure
block_cipher = None

# Collect any additional data files if needed
datas = []
binaries = []
hiddenimports = []

# Add all source files
a = Analysis(
    ['../main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VideoDiffTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/logo.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    a.zipfiles,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VideoDiffTool',
)

app = BUNDLE(
    coll,
    name='VideoDiffTool.app',
    icon='assets/logo.ico',
    bundle_identifier='com.videodifftool.app',
    info_plist={
        'NSDesktopFolderUsageDescription': 'Video Diff Tool needs access to the Desktop to save screenshots.',
        'NSDocumentsFolderUsageDescription': 'Video Diff Tool needs access to Documents to save screenshots.',
        'NSHighResolutionCapable': 'True'
    },
)

