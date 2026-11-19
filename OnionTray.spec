# PyInstaller build:  .venv\Scripts\pyinstaller --noconfirm OnionTray.spec
import os
import re

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

ROOT = os.path.abspath(SPECPATH)
with open(os.path.join(ROOT, "version.py"), encoding="utf-8") as f:
    VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', f.read()).group(1)
VERSION_TUPLE = tuple((list(map(int, VERSION.split("."))) + [0, 0, 0, 0])[:4])

# Python modules the app never imports.
EXCLUDED_MODULES = [
    "tkinter", "unittest", "pydoc", "ssl", "_ssl", "_hashlib", "PyQt6.QtNetwork", "PyQt6.QtQml", "PyQt6.QtQuick",
    "PyQt6.QtPdf", "PyQt6.QtOpenGL", "PyQt6.QtOpenGLWidgets", "PyQt6.QtSvg", "PyQt6.QtDBus",
    "multiprocessing", "concurrent", "email", "xml", "xmlrpc", "pyexpat", "urllib", "http", "html",
    "decimal", "_decimal", "_pydecimal", "fractions", "csv", "ftplib", "bz2", "_bz2", "lzma", "_lzma",
]
# Qt files pulled in by the PyQt6 hooks that a tray app does not need.
# opengl32sw.dll alone is ~20 MB (software OpenGL fallback).
EXCLUDED_FILES = (
    "opengl32sw", "d3dcompiler", "qt6quick", "qt6qml", "qt6pdf", "qt6network",
    "qt6opengl", "qt6svg", "qt6virtualkeyboard", "qt6dbus", "/translations/",
    "libcrypto", "libssl",  # no network access; hashlib falls back to built-ins
    "qoffscreen", "qminimal", "qdirect2d", "/generic/", "/iconengines/",  # only the Windows platform is used
)
KEEP_IMAGE_FORMATS = ("qico",)  # only the .ico loader is used


def keep(entry):
    name = entry[0].lower().replace("\\", "/")
    if "/plugins/imageformats/" in name:
        return any(fmt in name for fmt in KEEP_IMAGE_FORMATS)
    return not any(part in name for part in EXCLUDED_FILES)


a = Analysis(
    ["main.py"],
    pathex=[ROOT],
    datas=[("assets/icon.ico", "assets")],
    excludes=EXCLUDED_MODULES,
)
a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if keep(d)]

pyz = PYZ(a.pure)

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=VERSION_TUPLE, prodvers=VERSION_TUPLE),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("FileDescription", "OnionTray keyboard battery monitor"),
            StringStruct("ProductName", "OnionTray"),
            StringStruct("FileVersion", VERSION),
            StringStruct("ProductVersion", VERSION),
            StringStruct("OriginalFilename", "OnionTray.exe"),
            StringStruct("LegalCopyright", "MIT License"),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OnionTray",
    console=False,
    icon=os.path.join(ROOT, "assets", "icon.ico"),
    version=version_info,
    upx=False,
)
