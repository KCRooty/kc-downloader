"""Panel de herramientas: estado, versión, origen, instalar/actualizar y ruta manual."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
                               QHBoxLayout, QHeaderView, QLabel, QProgressBar, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import tools
from ..config import Settings
from ..tools import TOOLS, ToolManager
from .widgets import label

ORIGIN_LABEL = {"app": "Gestionada por la app", "release": "Incluida en la descarga",
                "sistema": "Del sistema", "manual": "Elegida a mano"}


class _Bridge(QObject):
    status = Signal(str, object)          # key, (version, origin, path) | None
    progress = Signal(str, int, int)      # key, hecho, total
    done = Signal(str, str)               # key, error ("" = bien)
    message = Signal(str)


class ToolsPanel(QWidget):
    changed = Signal()                    # alguna herramienta se instaló o cambió de ruta

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._busy: set[str] = set()
        self._b = _Bridge()
        self._b.status.connect(self._set_status)
        self._b.progress.connect(self._set_progress)
        self._b.done.connect(self._install_done)
        self._b.message.connect(lambda m: self.msg.setText(m))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        intro = label("KC Downloader usa estas herramientas libres. Si falta alguna, la descarga e instala "
                      "en tu carpeta de usuario (no hace falta ser administrador).", "Small")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        self.table = QTableWidget(len(TOOLS), 4)
        self.table.setHorizontalHeaderLabels(["Herramienta", "Versión", "Origen", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setShowGrid(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._bars: dict[str, QProgressBar] = {}
        self._install_btns: dict[str, QPushButton] = {}
        for row, (key, spec) in enumerate(TOOLS.items()):
            name = QTableWidgetItem(spec.label + ("" if spec.required else "  (opcional)"))
            name.setToolTip(spec.purpose)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem("…"))
            self.table.setItem(row, 2, QTableWidgetItem(""))
            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(4, 2, 4, 2)
            cl.setSpacing(6)
            bar = QProgressBar()
            bar.setFixedWidth(90)
            bar.setTextVisible(False)
            bar.hide()
            inst = QPushButton("Instalar")
            inst.clicked.connect(lambda _=False, k=key: self.install(k))
            pick = QPushButton("Ruta…")
            pick.setToolTip("Usar un ejecutable concreto de tu sistema")
            pick.clicked.connect(lambda _=False, k=key: self._pick(k))
            cl.addWidget(bar)
            cl.addWidget(inst)
            cl.addWidget(pick)
            self.table.setCellWidget(row, 3, cell)
            self._bars[key] = bar
            self._install_btns[key] = inst
        self.table.resizeRowsToContents()
        lay.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.auto = QCheckBox("Actualizar yt-dlp automáticamente (YouTube cambia a menudo)")
        self.auto.setChecked(settings.auto_update)
        self.auto.toggled.connect(lambda v: setattr(self.settings, "auto_update", v))
        self.all_btn = QPushButton("Instalar lo que falta")
        self.all_btn.clicked.connect(self.install_missing)
        self.upd_btn = QPushButton("Actualizar todo")
        self.upd_btn.clicked.connect(self.update_all)
        row.addWidget(self.auto, 1)
        row.addWidget(self.all_btn)
        row.addWidget(self.upd_btn)
        lay.addLayout(row)
        self.msg = label("", "Small")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        self.refresh()

    # ── estado
    def _tm(self) -> ToolManager:
        return ToolManager(self.settings.tool_paths)

    def refresh(self) -> None:
        tm = self._tm()
        for key in TOOLS:
            if key not in self._busy:
                self._row(key, 1).setText("comprobando…")

        def work():
            for key in TOOLS:
                f = tm.find(key)
                self._b.status.emit(key, (tm.version(key), f.origin, str(f.path)) if f else None)
        threading.Thread(target=work, daemon=True).start()

    def _row(self, key: str, col: int) -> QTableWidgetItem:
        return self.table.item(list(TOOLS).index(key), col)

    def _set_status(self, key: str, info) -> None:
        if key in self._busy:
            return
        ver, orig, path = (info or (None, None, ""))
        spec = TOOLS[key]
        if info:
            self._row(key, 1).setText(ver or "no responde")
            self._row(key, 2).setText(ORIGIN_LABEL.get(orig, orig))
            self._row(key, 2).setToolTip(path)
            btn = self._install_btns[key]
            if orig in ("app", "release"):
                btn.setText("Actualizar")
                btn.setToolTip("Descargar la última versión oficial")
            else:
                btn.setText("Usar copia propia")
                btn.setToolTip("Descargar una copia gestionada por la app, que se usará en vez de esta")
        else:
            self._row(key, 1).setText("falta" if spec.required else "no instalada")
            self._row(key, 2).setText("")
            self._install_btns[key].setText("Instalar")

    # ── acciones
    def _pick(self, key: str) -> None:
        f, _ = QFileDialog.getOpenFileName(self, f"Elegir {TOOLS[key].label}", "",
                                           "Ejecutables (*.exe)" if tools.IS_WINDOWS else "")
        if f:
            self.settings.tool_paths[key] = f
        elif key in self.settings.tool_paths:
            del self.settings.tool_paths[key]       # cancelar = volver a la búsqueda automática
        self.refresh()
        self.changed.emit()

    def install(self, key: str) -> None:
        if key in self._busy:
            return
        self._busy.add(key)
        self._install_btns[key].setEnabled(False)
        bar = self._bars[key]
        bar.setRange(0, 0)
        bar.show()
        self._row(key, 1).setText("descargando…")

        def work():
            try:
                tools.install(key, progress=lambda d, t: self._b.progress.emit(key, d, t),
                              log=lambda m: self._b.message.emit(m))
                self._b.done.emit(key, "")
            except Exception as e:
                self._b.done.emit(key, str(e))
        threading.Thread(target=work, daemon=True).start()

    def _set_progress(self, key: str, done: int, total: int) -> None:
        bar = self._bars[key]
        if total:
            bar.setRange(0, total)
            bar.setValue(done)
        self._row(key, 1).setText(f"{done / 1048576:.1f} MB" + (f" de {total / 1048576:.1f}" if total else ""))

    def _install_done(self, key: str, err: str) -> None:
        self._busy.discard(key)
        self._bars[key].hide()
        self._install_btns[key].setEnabled(True)
        if err:
            self.msg.setText(f"No se pudo instalar {TOOLS[key].label}: {err}")
        # Una instalación nueva manda sobre una ruta manual antigua de la misma herramienta.
        elif key in self.settings.tool_paths:
            del self.settings.tool_paths[key]
        self.refresh()
        self.changed.emit()

    def install_missing(self) -> None:
        tm = self._tm()
        missing = [k for k in TOOLS if not tm.find(k) and (TOOLS[k].required or k == "spotdl")]
        if not missing:
            self.msg.setText("No falta nada.")
        for k in missing:
            self.install(k)

    def update_all(self) -> None:
        tm = self._tm()
        for k in TOOLS:
            f = tm.find(k)
            # Las del sistema o elegidas a mano las actualiza su dueño, no la app.
            if f and f.origin in ("app", "release"):
                self.install(k)

    def is_busy(self) -> bool:
        return bool(self._busy)


class ToolsDialog(QDialog):
    """Primer arranque, o cuando falta algo imprescindible."""

    def __init__(self, settings: Settings, missing: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Herramientas necesarias")
        self.resize(720, 420)
        lay = QVBoxLayout(self)
        names = ", ".join(TOOLS[k].label for k in missing)
        head = QLabel(f"Faltan herramientas para descargar: <b>{names}</b>. "
                      "Pulsa «Instalar lo que falta» (unos 150 MB, solo la primera vez).")
        head.setWordWrap(True)
        lay.addWidget(head)
        self.panel = ToolsPanel(settings, self)
        lay.addWidget(self.panel, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def reject(self) -> None:
        if self.panel.is_busy():
            self.panel.msg.setText("Espera a que terminen las descargas de herramientas.")
            return
        super().reject()
