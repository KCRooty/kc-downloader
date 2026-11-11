"""Piezas de interfaz reutilizables."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFontMetrics
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QProgressBar,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from .. import paths
from ..jobs import STATUS_LABEL, Job
from ..sources import SOURCES
from .theme import SOURCE_COLORS


def card(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setObjectName("Card")
    return f


def label(text: str = "", name: str = "", parent=None) -> QLabel:
    lb = QLabel(text, parent)
    if name:
        lb.setObjectName(name)
    return lb


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)


def open_path(path: str | Path, select: bool = False) -> None:
    """Abre una carpeta, o la carpeta de un archivo con él seleccionado (Windows)."""
    p = Path(path)
    if select and p.is_file() and paths.IS_WINDOWS:
        subprocess.Popen(["explorer", "/select,", str(p)])
        return
    target = p if p.is_dir() else p.parent
    target.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


class ElideLabel(QLabel):
    """QLabel que recorta con «…» en vez de ensanchar la ventana."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(40)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 (API de Qt)
        self._full = text
        self.setToolTip(text)
        self._elide()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._elide()

    def _elide(self) -> None:
        fm = QFontMetrics(self.font())
        super().setText(fm.elidedText(self._full, Qt.ElideRight, max(10, self.width())))


class Segmented(QWidget):
    """Grupo de botones exclusivos (Audio / Vídeo / Imagen)."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for i, (value, text) in enumerate(options):
            b = QPushButton(text)
            b.setObjectName("Segment")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("pos", "first" if i == 0 else "last" if i == len(options) - 1 else "mid")
            bold = b.font()
            bold.setBold(True)
            b.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(text) + 36)   # marcado va en negrita
            self._group.addButton(b)
            self._buttons[value] = b
            lay.addWidget(b)
            b.toggled.connect(lambda on, v=value: on and self.changed.emit(v))

    def value(self) -> str:
        return next((v for v, b in self._buttons.items() if b.isChecked()), "")

    def set_value(self, value: str) -> None:
        if value in self._buttons:
            self._buttons[value].setChecked(True)


class JobRow(QFrame):
    """Una descarga en la cola."""

    retry = Signal(int)
    cancel = Signal(int)
    remove = Signal(int)

    def __init__(self, job: Job, parent=None):
        super().__init__(parent)
        self.job_id = job.id
        self.setObjectName("JobRow")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.badge = label(SOURCES.get(job.source, job.source), "Badge")
        c = QColor(SOURCE_COLORS.get(job.source, "#888888"))
        # Qt lee "#RRGGBBAA" como "#AARRGGBB": el tinte va con rgba()
        self.badge.setStyleSheet(f"background: rgba({c.red()},{c.green()},{c.blue()},0.16); color: {c.name()};")
        self.title = ElideLabel()
        self.title.setStyleSheet("font-weight: 600;")
        self.status = label("", "Small")
        top.addWidget(self.badge)
        top.addWidget(self.title, 1)
        top.addWidget(self.status)

        self.btn_open = self._ghost("Abrir", "Abrir la carpeta del archivo")
        self.btn_retry = self._ghost("Reintentar", "Volver a intentarlo")
        self.btn_cancel = self._ghost("Cancelar", "Detener esta descarga")
        self.btn_remove = self._ghost("Quitar", "Quitar de la cola")
        for b in (self.btn_open, self.btn_retry, self.btn_cancel, self.btn_remove):
            top.addWidget(b)
        self.btn_open.clicked.connect(self._open)
        self.btn_retry.clicked.connect(lambda: self.retry.emit(self.job_id))
        self.btn_cancel.clicked.connect(lambda: self.cancel.emit(self.job_id))
        self.btn_remove.clicked.connect(lambda: self.remove.emit(self.job_id))

        self.detail = ElideLabel()
        self.detail.setObjectName("Small")
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        root.addLayout(top)
        root.addWidget(self.detail)
        root.addWidget(self.bar)
        self._files: list[str] = []
        self._out_dir = ""

    def _ghost(self, text: str, tip: str) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("Ghost")
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _open(self) -> None:
        if self._files and os.path.exists(self._files[-1]):
            open_path(self._files[-1], select=True)
        elif self._out_dir:
            open_path(self._out_dir)

    def refresh(self, job: Job, out_dir: str) -> None:
        self._files, self._out_dir = list(job.files), out_dir
        self.title.setText(job.title or job.url)
        st = job.status
        self.status.setText(STATUS_LABEL.get(st, st))
        self.status.setObjectName({"done": "StatusOk", "error": "StatusErr", "running": "StatusWarn"}.get(st, "Small"))
        repolish(self.status)

        bits = [job.quality_label()]
        if job.item:
            bits.append(f"pista {job.item}" if job.source == "spotify" else f"elemento {job.item}")
        if st == "running":
            if job.percent >= 0:
                bits.append(f"{job.percent:.0f} %")
            if job.speed:
                bits.append(job.speed)
            if job.eta:
                bits.append(f"quedan {job.eta}")
        elif st == "error" and job.error:
            bits.append(job.error)
        elif st == "done" and job.files:
            bits.append(f"{len(job.files)} archivo(s)")
        self.detail.setText("  ·  ".join(bits))
        if st == "error":
            self.detail.setToolTip(job.error)

        if st == "running" and job.percent < 0:
            self.bar.setRange(0, 0)               # indeterminada mientras arranca
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(10 * (100 if st == "done" else max(0.0, job.percent))))
        self.bar.setProperty("state", st)
        repolish(self.bar)
        self.bar.setVisible(st in ("running", "done", "error"))

        self.btn_cancel.setVisible(st in ("running", "queued"))
        self.btn_retry.setVisible(st in ("error", "cancelled"))
        self.btn_open.setVisible(st == "done")
        self.btn_remove.setVisible(st != "running")
