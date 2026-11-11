"""Prueba de humo de la interfaz sin pantalla (QT_QPA_PLATFORM=offscreen).

Abre la ventana, añade enlaces, descarga uno de verdad si se pide
(--download) y guarda capturas de la ventana y de cada página de Ajustes.

  python tests/gui_smoke.py <carpeta_capturas> [--download] [--theme dark|light]
"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KCDL_HOME", tempfile.mkdtemp(prefix="kcdl-gui-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from kcdl import config  # noqa: E402
from kcdl.ui import theme  # noqa: E402
from kcdl.ui.main_window import MainWindow  # noqa: E402
from kcdl.ui.settings_dialog import SettingsDialog  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
download = "--download" in sys.argv
th = sys.argv[sys.argv.index("--theme") + 1] if "--theme" in sys.argv else "dark"

app = QApplication(sys.argv)
s = config.load()
s.theme = th
s.dir_audio = str(Path(os.environ["KCDL_HOME"]) / "A")
s.dir_video = str(Path(os.environ["KCDL_HOME"]) / "V")
s.auto_update = False
if "--tools" in sys.argv:   # carpeta tools/ de una release: se fijan como rutas manuales
    from kcdl import tools as _t
    tdir = Path(sys.argv[sys.argv.index("--tools") + 1])
    for key, spec in _t.TOOLS.items():
        p = (tdir / spec.subdir if spec.subdir else tdir) / _t.exe_name(spec.exe)
        if p.is_file():
            s.tool_paths[key] = str(p)
theme.apply(app, s.theme, s.accent, s.font_size)
w = MainWindow(s)
w.resize(980, 700)
w.show()


def pump(sec: float) -> None:
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


pump(0.6)
w.grab().save(str(out / f"{th}-0-vacia.png"))

w._add_text("https://www.youtube.com/watch?v=jNQXAC9IVRw\nhttps://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
w.mode.set_value("video")
w._add_text("https://www.youtube.com/watch?v=jNQXAC9IVRw")
w._add_text("https://www.pinterest.com/pin/123456/")
pump(0.3)
w.grab().save(str(out / f"{th}-1-cola.png"))
print("trabajos:", [(j.source, j.mode, j.quality_label()) for j in w.q.jobs])

if download:
    w.mode.set_value("audio")
    # solo los dos primeros (YouTube audio + Spotify): Pinterest /pin/123456 no existe
    for j in w.q.jobs[2:]:
        w.q.remove(j.id)
    pump(0.2)
    w._start()
    t0 = time.time()
    shot = False
    while w.q.is_busy() or any(j.status == "queued" for j in w.q.jobs):
        pump(0.2)
        if not shot and any(j.status == "running" and j.percent > 0 for j in w.q.jobs):
            w.grab().save(str(out / f"{th}-2-descargando.png"))
            shot = True
        if time.time() - t0 > 240:
            print("TIMEOUT")
            break
    pump(0.3)
    w.grab().save(str(out / f"{th}-3-terminado.png"))
    for j in w.q.jobs:
        print("resultado:", j.source, j.status, j.title, j.files, j.error)

dlg = SettingsDialog(s, w)
dlg.resize(860, 580)
dlg.show()
for i in range(dlg.nav.count()):
    dlg.nav.setCurrentRow(i)
    pump(4.0 if i == dlg.nav.count() - 1 else 0.2)   # spotdl --version tarda ~2 s
    dlg.grab().save(str(out / f"{th}-ajustes-{i}.png"))
dlg.reject()
w.close()
print("ok", out)
