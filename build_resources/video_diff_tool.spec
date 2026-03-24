# PyInstaller Spec file for Video Diff Tool
#
# To build:
# pyinstaller video_diff_tool.spec

from pathlib import Path
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules, copy_metadata

# Analyze the project structure
block_cipher = None
spec_dir = Path(globals().get("SPECPATH", Path.cwd() / "build_resources")).resolve()
project_root = spec_dir.parent
assets_dir = spec_dir / "assets"

# Collect PyAV explicitly so packaged builds do not rely on implicit hooks only.
datas = copy_metadata("av")
binaries = collect_dynamic_libs("av")
hiddenimports = collect_submodules("av")

# Add all source files
a = Analysis(
    [str(project_root / 'main.py')],
    pathex=[str(project_root)],
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
    icon=str(assets_dir / 'logo.ico'),
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
    icon=str(assets_dir / 'logo.ico'),
    bundle_identifier='com.videodifftool.app',
    info_plist={
        'NSDesktopFolderUsageDescription': 'Video Diff Tool needs access to the Desktop to save screenshots.',
        'NSDocumentsFolderUsageDescription': 'Video Diff Tool needs access to Documents to save screenshots.',
        'NSHighResolutionCapable': 'True'
    },
)
