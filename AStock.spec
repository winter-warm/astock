# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
import os
import sys
from pathlib import Path

# Do not resolve Qt's Windows ICU imports against unrelated tools on PATH
# (e.g. Poppler's ICU exports versioned symbols instead of Windows' ABI).
os.environ['PATH'] = os.pathsep.join([
    str(Path(os.environ['SystemRoot']) / 'System32'), os.environ['SystemRoot'],
    str(Path(sys.executable).parent),
])

datas = collect_data_files('akshare')
datas += [('README.md', '.'), ('docs', 'docs')]
datas += [('assets/astock.ico', 'assets')]
datas += [('src/astock/course_content', 'astock/course_content')]
binaries = collect_dynamic_libs('py_mini_racer')
a = Analysis(
    ['desktop_entry.py'], pathex=['src'], binaries=binaries, datas=datas,
    hiddenimports=['astock.window', 'astock.engine', 'astock.market', 'astock.strategy',
                   'astock.validation', 'akshare', 'pandas', 'numpy', 'pyarrow.parquet'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
              'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
              'PySide6.QtQuick', 'PySide6.QtQml', 'tkinter', 'pytest', 'ruff', 'matplotlib', 'IPython'],
    noarchive=False,
)
# These are Windows 10/11 components, never private application runtimes.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in {'icuuc.dll', 'icuin.dll', 'ucrtbase.dll'}
              and not Path(entry[0]).name.lower().startswith('api-ms-win-')]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AStock', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon='assets/astock.ico')
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='AStock')
