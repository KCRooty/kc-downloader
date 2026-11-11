"""Arranque: registro a archivo, captura de errores, tema y ventana."""

from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler

from . import APP_NAME, __version__, config, paths


def _setup_logging() -> str:
    d = paths.data_dir()
    d.mkdir(parents=True, exist_ok=True)
    f = d / "kc-downloader.log"
    h = RotatingFileHandler(f, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger("kcdl")
    root.setLevel(logging.INFO)
    root.addHandler(h)
    root.info("─── %s %s (%s, Python %s)", APP_NAME, __version__, sys.platform, sys.version.split()[0])
    return str(f)


def main() -> int:
    log_file = _setup_logging()

    from PySide6.QtWidgets import QApplication, QMessageBox

    from .ui import theme
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Static Forge")
    app.setDesktopFileName("kc-downloader")

    def excepthook(etype, value, tb):
        text = "".join(traceback.format_exception(etype, value, tb))
        logging.getLogger("kcdl").error("Error no controlado:\n%s", text)
        QMessageBox.critical(None, APP_NAME, f"Error inesperado:\n\n{value}\n\nDetalles en:\n{log_file}")

    sys.excepthook = excepthook

    s = config.load()
    selftest = "--selftest" in sys.argv
    if selftest:
        s.auto_update = False
    theme.apply(app, s.theme, s.accent, s.font_size)
    w = MainWindow(s)
    w.show()
    if selftest:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, lambda: _selftest_report(app))
    rc = app.exec()
    # Destruir la ventana antes que la QApplication: si lo decide el recolector de
    # Python en otro orden, Qt puede reventar al salir (visto en X11).
    w.close()
    w.deleteLater()
    del w
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    return rc


def _selftest_report(app) -> None:
    """Comprueba que la build trae lo necesario y escribe selftest.txt en la carpeta de datos."""
    from . import tools
    lines = [f"{APP_NAME} {__version__} frozen={paths.is_frozen()} app_dir={paths.app_dir()}"]
    try:
        import PIL
        lines.append(f"Pillow {PIL.__version__}")
    except ImportError as e:
        lines.append(f"FALLO Pillow: {e}")
    lines.append(f"Qt plataforma: {app.platformName()}")
    tm = tools.ToolManager()
    for key in tools.TOOLS:
        f = tm.find(key)
        lines.append(f"{key}: {f.origin + ' ' + str(f.path) + ' ' + str(tm.version(key)) if f else 'falta'}")
    out = paths.data_dir() / "selftest.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    app.quit()
