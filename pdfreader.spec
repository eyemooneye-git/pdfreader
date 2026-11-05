# -*- mode: python ; coding: utf-8 -*-

# One-file build: dist/pdfreader.exe
# Run: python -m PyInstaller --noconfirm --clean pdfreader.spec

from pathlib import Path

import PySide6

qt_translations = Path(PySide6.__file__).resolve().parent / "translations"

a = Analysis(
    ["run_pdfreader.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("assets/pdfreader.ico", "assets"),
        ("sample/demo.pdf", "sample"),
        (str(qt_translations / "qtbase_zh_CN.qm"), "translations"),
    ],
    hiddenimports=["pymupdf"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtQuickWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebChannel",
        "PySide6.QtWebSockets",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.Qt3DAnimation",
        "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic",
        "PySide6.Qt3DExtras",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtSql",
        "PySide6.QtDesigner",
        "PySide6.QtHelp",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtPositioning",
        "PySide6.QtSerialPort",
        "PySide6.QtBluetooth",
        "PySide6.QtSensors",
        "PySide6.QtNfc",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtStateMachine",
        "PySide6.QtTextToSpeech",
        "PySide6.QtUiTools",
        "PySide6.QtSvg",
        "PySide6.QtSvgWidgets",
        "tkinter",
        "unittest",
        "pydoc",
        "doctest",
        "pytest",
        # PyMuPDF optionally uses these for table/layout helpers and
        # Pixmap.numpy().  pdfreader only renders, extracts text and searches.
        "numpy",
        "pandas",
        "openpyxl",
        "lxml",
        "dateutil",
        "pytz",
        "six",
        "PIL",
        "pyarrow",
        "numba",
        "scipy",
        "matplotlib",
        "IPython",
        "sqlalchemy",
        "tabulate",
        "tqdm",
        "onnxruntime",
        "pymupdf4llm",
        "pymupdf_layout",
        "pymupdf_rag",
    ],
    noarchive=False,
    optimize=1,
)

# ---------------------------------------------------------------------------
# Trim the Qt runtime.  pdfreader is a pure QtWidgets app: it never uses
# QtQuick/OpenGL, SVG assets, TLS sockets or non-English Qt strings, but the
# PySide6 hooks collect those plugin folders and all translation files anyway.
# Note that QSettings itself lives in QtCore and cannot be dropped; it is
# simply pointed at an INI file by pdfreader/paths.py.
_UNUSED_BINARIES = (
    "opengl32sw.dll",
    "qt6svg.dll",
    "plugins\\generic\\qtuiotouchplugin.dll",
    "plugins\\iconengines\\qsvgicon.dll",
    "plugins\\imageformats\\qgif.dll",
    "plugins\\imageformats\\qicns.dll",
    "plugins\\imageformats\\qjpeg.dll",
    "plugins\\imageformats\\qsvg.dll",
    "plugins\\imageformats\\qtga.dll",
    "plugins\\imageformats\\qtiff.dll",
    "plugins\\imageformats\\qwbmp.dll",
    "plugins\\imageformats\\qwebp.dll",
    "plugins\\networkinformation\\qnetworklistmanager.dll",
    "plugins\\platforms\\qdirect2d.dll",
    "plugins\\platforms\\qminimal.dll",
    "plugins\\platforms\\qoffscreen.dll",
    "plugins\\styles\\qmodernwindowsstyle.dll",
    "plugins\\tls\\qcertonlybackend.dll",
    "plugins\\tls\\qopensslbackend.dll",
    "plugins\\tls\\qschannelbackend.dll",
)

a.binaries = [
    entry
    for entry in a.binaries
    if not entry[0].replace("/", "\\").lower().endswith(_UNUSED_BINARIES)
]

# Only the Simplified Chinese Qt strings are shipped; English is built into Qt
# and the app carries its own English dictionary.
a.datas = [
    entry
    for entry in a.datas
    if not entry[0].replace("/", "\\").lower().startswith("pyside6\\translations\\")
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="pdfreader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/pdfreader.ico",
    version="version_info.txt",
)
