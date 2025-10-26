# PyInstaller one-file build spec for SMDB
# Note: For bundled data (e.g., 'collections') to be found at runtime
# in one-file mode, the app code should resolve resources via
# getattr(sys, '_MEIPASS', os.getcwd()). Without that tweak, defaults
# that rely on './collections' may not be found unless the setting is
# configured by the user.

import os
from glob import glob
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.building.build_main import Analysis, PYZ, EXE

# Resolve paths relative to the current working directory (the repo root when using MakeExe.bat)
REPO_ROOT = os.path.abspath(os.getcwd())

datas = collect_data_files('imdb', include_py_files=False)
collections_glob = os.path.join(REPO_ROOT, 'smdb', 'collections', '*')
datas += [(path, 'collections') for path in glob(collections_glob) if os.path.isfile(path)]

binaries = []
mediainfo_dll = os.path.join(REPO_ROOT, 'smdb', 'MediaInfo.dll')
if os.path.exists(mediainfo_dll):
    binaries.append((mediainfo_dll, '.'))

a = Analysis(
    [os.path.join(REPO_ROOT, 'smdb', '__main__.py')],
    pathex=[REPO_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='SMDB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
