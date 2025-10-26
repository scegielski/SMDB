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

datas = collect_data_files('imdb', include_py_files=False)
datas += [(path, 'collections') for path in glob('src/collections/*') if os.path.isfile(path)]

binaries = []
if os.path.exists('MediaInfo.dll'):
    binaries.append(('MediaInfo.dll', '.'))

a = Analysis(
    ['run.py'],
    pathex=['.'],
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
