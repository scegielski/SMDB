# -*- mode: python ; coding: utf-8 -*-

import os
from glob import glob
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.building.build_main import COLLECT

# Resolve paths relative to the current working directory (the repo root when using MakeExe.bat)
REPO_ROOT = os.path.abspath(os.getcwd())

# Bundle MediaInfo.dll if present, IMDb data, and the collections folder
datas = []
mediainfo_dll = os.path.join(REPO_ROOT, 'smdb', 'MediaInfo.dll')
if os.path.exists(mediainfo_dll):
    datas.append((mediainfo_dll, '.'))

datas += collect_data_files('imdb', include_py_files=False)
collections_glob = os.path.join(REPO_ROOT, 'smdb', 'collections', '*')
datas += [(path, 'collections') for path in glob(collections_glob) if os.path.isfile(path)]

# Bundle shader files for OpenGL rendering
shader_files = ['vertex_shader.glsl', 'fragment_shader.glsl']
for shader in shader_files:
    shader_path = os.path.join(REPO_ROOT, 'smdb', shader)
    if os.path.exists(shader_path):
        datas.append((shader_path, 'smdb'))

a = Analysis(
    [os.path.join(REPO_ROOT, 'smdb', '__main__.py')],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=datas,
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
    [],
    name='SMDB',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SMDB-onedir',
)
