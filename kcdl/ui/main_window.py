"""Ventana principal."""

from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import QByteArray, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFontDatabase, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QPlainTextEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__, config, paths, tools
from ..config import Settings
from ..jobs import Job
from ..sources import SOURCES, detect_source, extract_urls
from . import theme
from .queue import QueueController
from .settings_dialog import SettingsDialog
from .tools_panel import ToolsDialog
from .widgets import JobRow, Segmented, card, label, open_path

log = logging.getLogger("kcdl")


class _Bg(QObject):
    message = Signal(str)
    checked = Signal()


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.s = settings
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(760, 560)
        icon = paths.resource_path("assets", "logo.png")
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))
        self.setAcceptDrops(True)

        self.q = QueueController(self.s, self)
        self.q.job_added.connect(self._on_added)
        self.q.job_changed.connect(self._on_changed)
        self.q.job_removed.connect(self._on_removed)
        self.q.log.connect(self._append_log)
        self.q.activity.connect(self._on_activity)
        self._rows: dict[int, tuple[QListWidgetItem, JobRow]] = {}
        self._bg = _Bg()
        self._bg.message.connect(self._append_log)
        self._bg.checked.connect(lambda: config.save(self.s))

        self._build()
        self._load_quick_from_settings()
        if self.s.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(self.s.window_geometry.encode()))
        else:
            self.resize(960, 680)
        QTimer.singleShot(200, self._startup)

    # ── construcción
    def _build(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.addWidget(label(APP_NAME, "Title"))
        ver = label(f"v{__version__}", "Small")
        head.addWidget(ver, 0, Qt.AlignBottom)
        head.addStretch(1)
        self.tools_btn = QPushButton("Herramientas")
        self.tools_btn.setObjectName("Ghost")
        self.tools_btn.clicked.connect(lambda: self._open_settings("Herramientas"))
        settings_btn = QPushButton("Ajustes")
        settings_btn.clicked.connect(lambda: self._open_settings())
        head.addWidget(self.tools_btn)
        head.addWidget(settings_btn)
        root.addLayout(head)

        # Entrada
        inp = card()
        il = QVBoxLayout(inp)
        il.setContentsMargins(14, 14, 14, 12)
        il.setSpacing(10)
        row = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setObjectName("UrlInput")
        self.url.setPlaceholderText("Pega uno o varios enlaces de YouTube, YouTube Music, Spotify o Pinterest")
        self.url.setClearButtonEnabled(True)
        self.url.returnPressed.connect(self._add_from_input)
        add = QPushButton("Añadir")
        add.setObjectName("Primary")
        add.clicked.connect(self._add_from_input)
        row.addWidget(self.url, 1)
        row.addWidget(add)
        il.addLayout(row)

        opts = QHBoxLayout()
        opts.setSpacing(10)
        self.mode = Segmented([("audio", "Audio"), ("video", "Vídeo"), ("image", "Imagen")])
        self.mode.changed.connect(self._mode_changed)
        opts.addWidget(self.mode)
        self.quick = QStackedWidget()
        self.quick.addWidget(self._quick_audio())
        self.quick.addWidget(self._quick_video())
        self.quick.addWidget(self._quick_image())
        opts.addWidget(self.quick, 1)
        self.folder_btn = QPushButton("Carpeta")
        self.folder_btn.setObjectName("Ghost")
        self.folder_btn.clicked.connect(lambda: open_path(self.s.output_dir(self.mode.value())))
        opts.addWidget(self.folder_btn)
        il.addLayout(opts)
        root.addWidget(inp)

        # Cola
        qh = QHBoxLayout()
        qh.addWidget(label("Cola", "SectionTitle"))
        self.counts = label("", "Small")
        qh.addWidget(self.counts)
        qh.addStretch(1)
        clear = QPushButton("Quitar terminadas")
        clear.setObjectName("Ghost")
        clear.clicked.connect(self.q.clear_finished)
        qh.addWidget(clear)
        root.addLayout(qh)

        self.queue_stack = QStackedWidget()
        empty = label("Pega un enlace arriba o arrástralo a la ventana.\n"
                      "Vídeos sueltos, playlists, álbumes y canciones de Spotify.", "Dim")
        empty.setAlignment(Qt.AlignCenter)
        self.list = QListWidget()
        self.list.setSpacing(4)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.queue_stack.addWidget(empty)
        self.queue_stack.addWidget(self.list)
        root.addWidget(self.queue_stack, 1)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.log_view.setFixedHeight(150)
        self.log_view.setVisible(self.s.show_log)
        root.addWidget(self.log_view)

        foot = QHBoxLayout()
        self.log_btn = QPushButton("Registro")
        self.log_btn.setCheckable(True)
        self.log_btn.setChecked(self.s.show_log)
        self.log_btn.toggled.connect(self.log_view.setVisible)
        foot.addWidget(self.log_btn)
        foot.addStretch(1)
        self.cancel_btn = QPushButton("Cancelar todo")
        self.cancel_btn.clicked.connect(self.q.cancel_all)
        self.cancel_btn.hide()
        self.start_btn = QPushButton("Descargar")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self._start)
        foot.addWidget(self.cancel_btn)
        foot.addWidget(self.start_btn)
        root.addLayout(foot)

        QShortcut(QKeySequence.Paste, self, activated=self._paste_anywhere)
        self._refresh_counts()

    def _quick_row(self) -> tuple[QWidget, QHBoxLayout]:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        return w, lay

    def _quick_audio(self) -> QWidget:
        w, lay = self._quick_row()
        self.q_afmt = QComboBox()
        self.q_afmt.addItems(config.AUDIO_FORMATS)
        self.q_akbps = QComboBox()
        for k in config.AUDIO_KBPS:
            self.q_akbps.addItem(f"{k} kbps", k)
        self.q_afmt.currentTextChanged.connect(self._quick_changed)
        self.q_akbps.currentIndexChanged.connect(self._quick_changed)
        lay.addWidget(self.q_afmt)
        lay.addWidget(self.q_akbps)
        lay.addStretch(1)
        return w

    def _quick_video(self) -> QWidget:
        w, lay = self._quick_row()
        self.q_res = QComboBox()
        self.q_res.addItems(config.VIDEO_RES)
        self.q_fps = QComboBox()
        for v in config.VIDEO_FPS:
            self.q_fps.addItem("Auto fps" if v == "Auto" else f"{v} fps", v)
        self.q_vfmt = QComboBox()
        self.q_vfmt.addItems(config.VIDEO_FORMATS)
        for c in (self.q_res, self.q_fps, self.q_vfmt):
            c.currentIndexChanged.connect(self._quick_changed)
            lay.addWidget(c)
        lay.addStretch(1)
        return w

    def _quick_image(self) -> QWidget:
        w, lay = self._quick_row()
        self.q_up = QCheckBox("Reescalar")
        self.q_upf = QComboBox()
        for f in (2, 3, 4):
            self.q_upf.addItem(f"x{f}", f)
        self.q_upe = QComboBox()
        self.q_upe.addItems(config.UPSCALE_ENGINES)
        self.q_up.toggled.connect(self._quick_changed)
        self.q_upf.currentIndexChanged.connect(self._quick_changed)
        self.q_upe.currentIndexChanged.connect(self._quick_changed)
        lay.addWidget(self.q_up)
        lay.addWidget(self.q_upf)
        lay.addWidget(self.q_upe)
        lay.addStretch(1)
        return w

    # ── controles rápidos ↔ ajustes
    def _load_quick_from_settings(self) -> None:
        self._loading = True
        s = self.s
        self.q_afmt.setCurrentText(s.audio_format)
        self.q_akbps.setCurrentIndex(max(0, self.q_akbps.findData(s.audio_kbps)))
        self.q_res.setCurrentText(s.video_res)
        self.q_fps.setCurrentIndex(max(0, self.q_fps.findData(s.video_fps)))
        self.q_vfmt.setCurrentText(s.video_format)
        self.q_up.setChecked(s.upscale_enabled)
        self.q_upf.setCurrentIndex(max(0, self.q_upf.findData(s.upscale_factor)))
        self.q_upe.setCurrentText(s.upscale_engine)
        self.mode.set_value(s.mode)
        self.quick.setCurrentIndex(config.MODES.index(s.mode))
        self._loading = False
        self._quick_changed()

    def _quick_changed(self, *_):
        lossless = self.q_afmt.currentText() in config.LOSSLESS_AUDIO
        self.q_akbps.setEnabled(not lossless)
        self.q_upf.setEnabled(self.q_up.isChecked())
        self.q_upe.setEnabled(self.q_up.isChecked())
        if getattr(self, "_loading", False):
            return
        s = self.s
        s.audio_format = self.q_afmt.currentText()
        s.audio_kbps = self.q_akbps.currentData()
        s.video_res = self.q_res.currentText()
        s.video_fps = self.q_fps.currentData()
        s.video_format = self.q_vfmt.currentText()
        s.upscale_enabled = self.q_up.isChecked()
        s.upscale_factor = self.q_upf.currentData()
        s.upscale_engine = self.q_upe.currentText()

    def _mode_changed(self, mode: str) -> None:
        self.s.mode = mode
        self.quick.setCurrentIndex(config.MODES.index(mode))

    # ── añadir
    def _add_from_input(self) -> None:
        if self._add_text(self.url.text()):
            self.url.clear()

    def _paste_anywhere(self) -> None:
        if self.url.hasFocus():
            self.url.paste()
            return
        self._add_text(QApplication.clipboard().text())

    def _add_text(self, text: str) -> bool:
        urls = extract_urls(text) or ([text.strip()] if text.strip() else [])
        if not urls:
            return False
        bad = []
        for u in urls:
            src = detect_source(u)
            if not src:
                bad.append(u)
                continue
            job = Job.from_settings(u, src, self.mode.value() or "audio", self.s)
            self.q.add(job, start=self.s.auto_start)
            self._append_log(f"+ {SOURCES[src]} · {job.quality_label()} · {u}")
        if bad:
            QMessageBox.warning(self, "Enlace no reconocido",
                                "Estos enlaces no son de YouTube, YouTube Music, Spotify ni Pinterest:\n\n"
                                + "\n".join(bad[:8]))
        return len(bad) < len(urls)

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasText() or e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        md = e.mimeData()
        text = md.text() if md.hasText() else "\n".join(u.toString() for u in md.urls())
        self._add_text(text)

    # ── cola
    def _on_added(self, job_id: int) -> None:
        job = self.q.get(job_id)
        row = JobRow(job)
        row.retry.connect(self.q.retry)
        row.cancel.connect(self.q.cancel)
        row.remove.connect(self.q.remove)
        item = QListWidgetItem()
        self.list.addItem(item)
        self.list.setItemWidget(item, row)
        self._rows[job_id] = (item, row)
        self._on_changed(job_id)
        self.queue_stack.setCurrentIndex(1)

    def _on_changed(self, job_id: int) -> None:
        job = self.q.get(job_id)
        pair = self._rows.get(job_id)
        if not job or not pair:
            return
        item, row = pair
        row.refresh(job, self.s.output_dir(job.mode))
        item.setSizeHint(row.sizeHint())
        self._refresh_counts()

    def _on_removed(self, job_id: int) -> None:
        pair = self._rows.pop(job_id, None)
        if pair:
            self.list.takeItem(self.list.row(pair[0]))
        if not self._rows:
            self.queue_stack.setCurrentIndex(0)
        self._refresh_counts()

    def _refresh_counts(self) -> None:
        c = self.q.counts()
        parts = []
        for key, txt in (("running", "descargando"), ("queued", "en cola"), ("done", "terminadas"),
                         ("error", "con error")):
            if c.get(key):
                parts.append(f"{c[key]} {txt}")
        self.counts.setText("  ·  ".join(parts))
        pending = c.get("queued", 0)
        self.start_btn.setEnabled(pending > 0)
        self.start_btn.setText(f"Descargar ({pending})" if pending > 1 else "Descargar")

    def _start(self) -> None:
        missing = tools.ToolManager(self.s.tool_paths).missing_required()
        if missing:
            self._show_tools_dialog(missing)
            if tools.ToolManager(self.s.tool_paths).missing_required():
                return
        self.q.start()

    def _on_activity(self, busy: bool) -> None:
        self.cancel_btn.setVisible(busy)
        self._refresh_counts()

    # ── registro
    def _append_log(self, msg: str) -> None:
        log.info(msg)
        self.log_view.appendPlainText(msg)

    # ── ajustes y herramientas
    def _open_settings(self, page: str = "") -> None:
        before = (self.s.theme, self.s.accent, self.s.font_size)
        dlg = SettingsDialog(self.s, self, start_page=page)
        app = QApplication.instance()
        dlg.preview.connect(lambda s: theme.apply(app, s.theme, s.accent, s.font_size))
        if dlg.exec():
            new = dlg.result_settings()
            new.window_geometry = self.s.window_geometry
            for f in new.__dataclass_fields__:
                setattr(self.s, f, getattr(new, f))
            config.save(self.s)
            self._load_quick_from_settings()
            self.log_view.setVisible(self.s.show_log or self.log_btn.isChecked())
        else:
            # Las herramientas instaladas desde el diálogo cuentan aunque se cancele.
            self.s.tool_paths = dict(dlg.s.tool_paths)
            self.s.theme, self.s.accent, self.s.font_size = before
        theme.apply(app, self.s.theme, self.s.accent, self.s.font_size)
        for jid in list(self._rows):
            self._on_changed(jid)
        self._update_tools_btn()

    def _show_tools_dialog(self, missing: list[str]) -> None:
        dlg = ToolsDialog(self.s, missing, self)
        dlg.exec()
        config.save(self.s)
        self._update_tools_btn()

    def _update_tools_btn(self) -> None:
        missing = tools.ToolManager(self.s.tool_paths).missing_required()
        self.tools_btn.setText("Faltan herramientas" if missing else "Herramientas")
        self.tools_btn.setStyleSheet("color: #F06A6A; font-weight: 600;" if missing else "")

    # ── arranque
    def _startup(self) -> None:
        self._update_tools_btn()
        tm = tools.ToolManager(self.s.tool_paths)
        missing = tm.missing_required()
        if missing:
            self._show_tools_dialog(missing)
        elif self.s.auto_update and time.time() - self.s.last_update_check > 86400:
            threading.Thread(target=self._auto_update, daemon=True).start()

    def _auto_update(self) -> None:
        """Actualiza yt-dlp una vez al día si es una copia de la app o de la release."""
        tm = tools.ToolManager(self.s.tool_paths)
        f = tm.find("yt-dlp")
        if not f or f.origin not in ("app", "release"):
            return
        current, latest = tm.version("yt-dlp"), tools.latest_ytdlp_version()
        self.s.last_update_check = time.time()
        if latest and current and latest != current:
            self._bg.message.emit(f"Actualizando yt-dlp {current} → {latest}…")
            try:
                tools.install("yt-dlp")
                self._bg.message.emit(f"yt-dlp actualizado a {latest}")
            except Exception as e:
                self._bg.message.emit(f"No se pudo actualizar yt-dlp: {e}")
        elif current:
            self._bg.message.emit(f"yt-dlp {current} está al día")
        self._bg.checked.emit()

    # ── cierre
    def closeEvent(self, e):  # noqa: N802
        if self.q.is_busy():
            r = QMessageBox.question(self, "Descargas en curso",
                                     "Hay descargas en marcha. ¿Cancelarlas y salir?")
            if r != QMessageBox.Yes:
                e.ignore()
                return
            self.q.cancel_all()
        self.s.window_geometry = bytes(self.saveGeometry().toBase64()).decode()
        self.s.show_log = self.log_btn.isChecked()
        config.save(self.s)
        super().closeEvent(e)
