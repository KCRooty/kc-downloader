"""Arranque: registro a archivo, captura de errores, tema y ventana."""

from __future__ import annotations

import logging
import os
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
    if "--download" in sys.argv:
        return _cli_download(sys.argv)

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


def _cli_download(argv: list[str]) -> int:
    """Descarga sin interfaz, con los mismos ajustes y herramientas que la app:
    KC Downloader --download URL [--mode audio|video|image] [--out CARPETA]

    El ejecutable de Windows no tiene consola, así que el registro completo y
    el resultado van también a download-test.txt en la carpeta de datos."""
    from . import jobs, sources, tools

    def arg(name: str, default: str = "") -> str:
        return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default

    url, mode, out = arg("--download"), arg("--mode", "audio"), arg("--out")
    report = paths.data_dir() / "download-test.txt"
    lines: list[str] = [f"{APP_NAME} {__version__} frozen={paths.is_frozen()} url={url} mode={mode}"]

    def say(msg: str) -> None:
        lines.append(msg)
        try:
            print(msg, flush=True)
        except (OSError, ValueError, AttributeError):   # sin consola
            pass

    src = sources.detect_source(url)
    if not src:
        say("RESULTADO error: enlace no reconocido")
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 2
    s = config.load()
    if out:
        s.dir_audio = s.dir_video = s.dir_image = out
    tm = tools.ToolManager(s.tool_paths)
    for key in tools.TOOLS:
        f = tm.find(key)
        say(f"{key}: {f.origin + ' ' + str(f.path) if f else 'falta'}")
    pyi = sorted(k for k in os.environ if k.startswith(("_PYI_", "_MEI", "LD_LIBRARY_PATH")))
    say(f"entorno de PyInstaller que no pasa a las herramientas: {pyi or 'ninguno'}")
    job =jobs.Job.from_settings(url, src, mode, s)

    def emit(kind: str, data) -> None:
        if kind == "log":
            say(str(data))

    jobs.Runner(job, s, tm, emit).run()
    say(f"RESULTADO {job.status}: {job.title} {list(job.files)} {job.error or ''}".rstrip())
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0 if job.status == "done" and all(os.path.isfile(f) for f in job.files) else 1


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
