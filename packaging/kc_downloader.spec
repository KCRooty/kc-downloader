# PyInstaller — KC Downloader en modo carpeta (onedir).
# Uso: pyinstaller packaging/kc_downloader.spec   (desde la raíz del repo)
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
IS_WIN = sys.platform.startswith("win")

binaries = []
if not IS_WIN:
    # El plugin X11 de Qt necesita estas xcb-util, que muchas distros no instalan de serie.
    # Se meten en el bundle si están en la máquina que compila (el CI las instala).
    for lib in ("libxcb-cursor.so.0", "libxcb-icccm.so.4", "libxcb-keysyms.so.1", "libxcb-shape.so.0",
                "libxcb-image.so.0", "libxcb-render-util.so.0", "libxcb-xkb.so.1", "libxkbcommon-x11.so.0"):
        for d in ("/usr/lib/x86_64-linux-gnu", "/usr/lib64", "/usr/lib"):
            if os.path.exists(f"{d}/{lib}"):
                binaries.append((f"{d}/{lib}", "."))
                break

a = Analysis(
    [str(ROOT / "kc_downloader.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=[(str(ROOT / "assets" / "logo.png"), "assets")],
    hiddenimports=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtBluetooth", "PySide6.QtLocation"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="KC Downloader" if IS_WIN else "kc-downloader",
    console=False,
    icon=str(ROOT / "assets" / "logo.ico") if IS_WIN and (ROOT / "assets" / "logo.ico").exists() else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="KC Downloader", upx=False)
