"""Rutas por plataforma: configuración, datos, herramientas y descargas.

KCDL_HOME (variable de entorno) redirige configuración y datos a una sola
carpeta: lo usan las pruebas y sirve para una instalación portable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
APP_DIR_NAME = "KC Downloader" if IS_WINDOWS else "kc-downloader"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Carpeta del ejecutable (empaquetado) o raíz del repo (desde código)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """Archivos de solo lectura que viajan con la app (logo, etc.)."""
    base = Path(getattr(sys, "_MEIPASS", app_dir()))
    return base.joinpath(*parts)


def _portable_home() -> Path | None:
    v = os.environ.get("KCDL_HOME", "").strip()
    return Path(v) if v else None


def config_dir() -> Path:
    home = _portable_home()
    if home:
        return home / "config"
    if IS_WINDOWS:
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_DIR_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / APP_DIR_NAME


def data_dir() -> Path:
    home = _portable_home()
    if home:
        return home / "data"
    if IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP_DIR_NAME
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_DIR_NAME


def managed_tools_dir() -> Path:
    """Herramientas que la app descarga y actualiza por su cuenta."""
    return data_dir() / "tools"


def bundled_tools_dir() -> Path:
    """Herramientas que vienen dentro del zip/tar de la release."""
    return app_dir() / "tools"


def downloads_dir() -> Path:
    if not IS_WINDOWS:
        try:
            out = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True,
                                 text=True, timeout=3).stdout.strip()
            if out and out != str(Path.home()):
                return Path(out)
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / "Downloads"


def default_output_root() -> Path:
    return downloads_dir() / "KC Downloader"
