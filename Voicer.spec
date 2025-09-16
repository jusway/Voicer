# -*- mode: python ; coding: utf-8 -*-

# PyInstaller spec for Voicer (onedir / windowed)
# Usage:
#   pyinstaller Voicer.spec

import os
from PyInstaller.utils.hooks import collect_all
from PyInstaller.building.datastruct import Tree

block_cipher = None

# Collect additional binaries/datas/hiddenimports from third-party packages
_datas = []
_binaries = []
_hiddenimports = ['wx.adv', 'wx.lib.scrolledpanel']

for mod in ('onnxruntime', 'soundfile'):
    try:
        d, b, h = collect_all(mod)
        _datas += d
        _binaries += b
        _hiddenimports += h
    except Exception:
        pass

# Bundle example config templates so users have references
_datas += [
    ('config/wx_gui_config.example.json', 'config'),
    ('config/wx_gui_api_keys.example.json', 'config'),
]

# Bundle UI images (optional)
# (Images will be added to _ext_trees after it is defined below.)

# Optionally include pre-fetched external assets if present
_ext_trees = []
if os.path.isdir('external/ffmpeg'):
    _ext_trees.append(Tree('external/ffmpeg', prefix='external/ffmpeg'))
if os.path.isdir('external/silero_vad'):
    _ext_trees.append(Tree('external/silero_vad', prefix='external/silero_vad'))


# Bundle UI images (optional)
if os.path.isdir('imgs'):
    _ext_trees.append(Tree('imgs', prefix='imgs'))

a = Analysis(
    ['run_gui.py'],
    pathex=[],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hooks/runtime_voicer.py'],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Voicer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # windowed
    icon='imgs/声稿师ICON.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    *_ext_trees,
    strip=False,
    upx=True,
    name='Voicer',
)