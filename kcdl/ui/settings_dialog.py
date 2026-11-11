"""Ventana de ajustes. Edita una copia; «Guardar» la devuelve, «Cancelar» la descarta."""

from __future__ import annotations

import dataclasses

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QListWidget,
                               QPushButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from .. import config
from ..config import Settings
from .tools_panel import ToolsPanel
from .widgets import label

THEME_LABELS = [("system", "Igual que el sistema"), ("dark", "Oscuro"), ("light", "Claro")]
BROWSER_LABELS = [("", "No usar"), ("chrome", "Chrome"), ("firefox", "Firefox"), ("edge", "Edge"),
                  ("brave", "Brave"), ("opera", "Opera"), ("vivaldi", "Vivaldi"), ("chromium", "Chromium")]

TEMPLATE_HELP = ("Campos útiles: %(title)s, %(uploader)s, %(artist)s, %(album)s, %(upload_date)s, %(id)s, "
                 "%(ext)s. Una «/» crea subcarpetas. «%(artist,uploader)s» usa el artista y, si no hay, el canal.")


def _combo(items: list[tuple[str, str]], current: str) -> QComboBox:
    c = QComboBox()
    for value, text in items:
        c.addItem(text, value)
    i = c.findData(current)
    c.setCurrentIndex(max(0, i))
    return c


def _plain(values: list, current) -> QComboBox:
    return _combo([(v, str(v)) for v in values], current)


def _page(title: str, subtitle: str = "") -> tuple[QWidget, QFormLayout]:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(4, 0, 4, 0)
    v.addWidget(label(title, "SectionTitle"))
    if subtitle:
        s = label(subtitle, "Small")
        s.setWordWrap(True)
        v.addWidget(s)
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    form.setHorizontalSpacing(14)
    form.setVerticalSpacing(10)
    v.addSpacing(8)
    v.addLayout(form)
    v.addStretch(1)
    return w, form


class FolderField(QWidget):
    def __init__(self, value: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(value)
        b = QPushButton("Elegir…")
        b.clicked.connect(self._pick)
        lay.addWidget(self.edit, 1)
        lay.addWidget(b)

    def _pick(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Elegir carpeta", self.edit.text())
        if d:
            self.edit.setText(d)

    def text(self) -> str:
        return self.edit.text().strip()


class SettingsDialog(QDialog):
    preview = Signal(object)          # Settings: vista previa del tema mientras se edita

    def __init__(self, settings: Settings, parent=None, start_page: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Ajustes")
        self.resize(820, 560)
        self.s = dataclasses.replace(settings, tool_paths=dict(settings.tool_paths))

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        body.setSpacing(14)
        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFixedWidth(190)
        self.stack = QStackedWidget()
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        self._pages: dict[str, int] = {}
        self._add("Apariencia", self._appearance())
        self._add("Carpetas y nombres", self._folders())
        self._add("Formatos", self._formats())
        self._add("Red y cuentas", self._network())
        self._add("Imágenes", self._images())
        self.tools_panel = ToolsPanel(self.s)
        tw = QWidget()
        tv = QVBoxLayout(tw)
        tv.setContentsMargins(4, 0, 4, 0)
        tv.addWidget(label("Herramientas", "SectionTitle"))
        tv.addWidget(self.tools_panel, 1)
        self._add("Herramientas", tw)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(self._pages.get(start_page, 0))

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("Guardar")
        bb.button(QDialogButtonBox.Save).setObjectName("Primary")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _add(self, name: str, w: QWidget) -> None:
        self._pages[name] = self.stack.count()
        self.stack.addWidget(w)
        self.nav.addItem(name)

    # ── páginas
    def _appearance(self) -> QWidget:
        w, f = _page("Apariencia")
        self.theme = _combo(THEME_LABELS, self.s.theme)
        self.theme.currentIndexChanged.connect(self._live)
        f.addRow("Tema", self.theme)

        sw = QWidget()
        sl = QHBoxLayout(sw)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(6)
        self._swatches: list[QPushButton] = []
        for col in config.ACCENT_PRESETS:
            b = QPushButton()
            b.setFixedSize(26, 26)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(col)
            b.clicked.connect(lambda _=False, c=col: self._set_accent(c))
            sl.addWidget(b)
            self._swatches.append(b)
        custom = QPushButton("Otro…")
        custom.clicked.connect(self._pick_accent)
        sl.addWidget(custom)
        sl.addStretch(1)
        f.addRow("Color de acento", sw)

        self.font_size = QSpinBox()
        self.font_size.setRange(8, 16)
        self.font_size.setValue(self.s.font_size)
        self.font_size.setSuffix(" pt")
        self.font_size.valueChanged.connect(self._live)
        f.addRow("Tamaño de letra", self.font_size)
        self.show_log = QCheckBox("Mostrar el registro al abrir")
        self.show_log.setChecked(self.s.show_log)
        f.addRow("", self.show_log)
        self._paint_swatches()
        return w

    def _folders(self) -> QWidget:
        w, f = _page("Carpetas y nombres", TEMPLATE_HELP)
        self.dir_audio = FolderField(self.s.dir_audio)
        self.dir_video = FolderField(self.s.dir_video)
        self.dir_image = FolderField(self.s.dir_image)
        f.addRow("Audio", self.dir_audio)
        f.addRow("Vídeo", self.dir_video)
        f.addRow("Imágenes", self.dir_image)
        self.tpl_audio = QLineEdit(self.s.tpl_audio)
        self.tpl_video = QLineEdit(self.s.tpl_video)
        self.tpl_spotify = QLineEdit(self.s.tpl_spotify)
        self.tpl_spotify.setToolTip("Solo cuando Spotify se descarga con spotDL. Campos: {artist}, {title}, "
                                    "{album}, {track-number}, {output-ext}")
        f.addRow("Nombre (audio)", self.tpl_audio)
        f.addRow("Nombre (vídeo)", self.tpl_video)
        f.addRow("Nombre (spotDL)", self.tpl_spotify)
        self.pl_folder = QCheckBox("Carpeta propia para cada playlist o álbum")
        self.pl_folder.setChecked(self.s.tpl_playlist_folder)
        f.addRow("", self.pl_folder)
        reset = QPushButton("Restablecer nombres")
        reset.clicked.connect(self._reset_templates)
        f.addRow("", reset)
        return w

    def _formats(self) -> QWidget:
        w, f = _page("Formatos por defecto", "Lo que sale elegido al abrir la app. Cada descarga puede cambiarlo.")
        self.audio_format = _plain(config.AUDIO_FORMATS, self.s.audio_format)
        self.audio_kbps = _combo([(k, f"{k} kbps") for k in config.AUDIO_KBPS], self.s.audio_kbps)
        f.addRow("Formato de audio", self.audio_format)
        f.addRow("Calidad de audio", self.audio_kbps)
        self.video_res = _plain(config.VIDEO_RES, self.s.video_res)
        self.video_fps = _combo([(v, "Automático" if v == "Auto" else f"{v} fps") for v in config.VIDEO_FPS],
                                self.s.video_fps)
        self.video_format = _plain(config.VIDEO_FORMATS, self.s.video_format)
        f.addRow("Resolución máxima", self.video_res)
        f.addRow("Fotogramas", self.video_fps)
        f.addRow("Contenedor de vídeo", self.video_format)
        self.embed_thumb = QCheckBox("Incrustar carátula")
        self.embed_thumb.setChecked(self.s.embed_thumbnail)
        self.embed_meta = QCheckBox("Incrustar metadatos (título, artista, álbum)")
        self.embed_meta.setChecked(self.s.embed_metadata)
        self.subs = QCheckBox("Incrustar subtítulos en los vídeos")
        self.subs.setChecked(self.s.subtitles)
        self.sub_langs = QLineEdit(self.s.sub_langs)
        self.sub_langs.setPlaceholderText("es,en")
        self.auto_start = QCheckBox("Empezar a descargar en cuanto se añade un enlace")
        self.auto_start.setChecked(self.s.auto_start)
        f.addRow("", self.embed_thumb)
        f.addRow("", self.embed_meta)
        f.addRow("", self.subs)
        f.addRow("Idiomas de subtítulos", self.sub_langs)
        f.addRow("", self.auto_start)
        return w

    def _network(self) -> QWidget:
        w, f = _page("Red y cuentas", "Las cookies sirven para vídeos con restricción de edad, privados o de "
                                      "miembros. Con «navegador» se leen directamente de tu sesión (cierra el "
                                      "navegador si da error de acceso a la base de datos de cookies).")
        self.browser = _combo(BROWSER_LABELS, self.s.cookies_browser)
        f.addRow("Cookies del navegador", self.browser)
        ck = QWidget()
        cl = QHBoxLayout(ck)
        cl.setContentsMargins(0, 0, 0, 0)
        self.cookies_file = QLineEdit(self.s.cookies_file)
        self.cookies_file.setPlaceholderText("cookies.txt en formato Netscape (opcional)")
        pick = QPushButton("Elegir…")
        pick.clicked.connect(self._pick_cookies)
        cl.addWidget(self.cookies_file, 1)
        cl.addWidget(pick)
        f.addRow("Archivo de cookies", ck)
        self.proxy = QLineEdit(self.s.proxy)
        self.proxy.setPlaceholderText("http://usuario:clave@host:puerto  o  socks5://host:1080")
        f.addRow("Proxy", self.proxy)
        self.concurrent = QSpinBox()
        self.concurrent.setRange(1, 6)
        self.concurrent.setValue(self.s.concurrent)
        f.addRow("Descargas a la vez", self.concurrent)
        self.rate = QLineEdit(self.s.rate_limit)
        self.rate.setPlaceholderText("sin límite  (ej.: 5M = 5 MB/s, 500K)")
        f.addRow("Límite de velocidad", self.rate)
        return w

    def _images(self) -> QWidget:
        w, f = _page("Imágenes", "Pinterest baja la imagen a la mayor resolución publicada. El reescalado crea "
                                 "una copia aparte (nombre_x2, nombre_x4) y no toca el original.")
        self.up_enabled = QCheckBox("Reescalar las imágenes descargadas")
        self.up_enabled.setChecked(self.s.upscale_enabled)
        self.up_factor = _combo([(2, "x2"), (3, "x3"), (4, "x4")], self.s.upscale_factor)
        self.up_engine = _combo([("Lanczos", "Lanczos (rápido, sin GPU)"),
                                 ("Real-ESRGAN", "Real-ESRGAN (IA, usa la GPU)")], self.s.upscale_engine)
        f.addRow("", self.up_enabled)
        f.addRow("Factor", self.up_factor)
        f.addRow("Motor", self.up_engine)
        return w

    # ── acento
    def _paint_swatches(self) -> None:
        cur = QColor(self.s.accent).name().lower()
        for b in self._swatches:
            col = b.toolTip()
            ring = "3px solid palette(text)" if col.lower() == cur else "1px solid palette(mid)"
            b.setStyleSheet(f"background: {col}; border: {ring}; border-radius: 13px; padding: 0;")

    def _set_accent(self, col: str) -> None:
        self.s.accent = col
        self._paint_swatches()
        self._live()

    def _pick_accent(self) -> None:
        c = QColorDialog.getColor(QColor(self.s.accent), self, "Color de acento")
        if c.isValid():
            self._set_accent(c.name())

    def _live(self) -> None:
        self.s.theme = self.theme.currentData()
        self.s.font_size = self.font_size.value()
        self.preview.emit(self.s)
        self._paint_swatches()

    def _reset_templates(self) -> None:
        d = Settings()
        self.tpl_audio.setText(d.tpl_audio)
        self.tpl_video.setText(d.tpl_video)
        self.tpl_spotify.setText(d.tpl_spotify)

    def _pick_cookies(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Archivo de cookies", self.cookies_file.text(),
                                           "Cookies (*.txt);;Todos (*)")
        if f:
            self.cookies_file.setText(f)

    # ── resultado
    def result_settings(self) -> Settings:
        s = self.s
        s.theme = self.theme.currentData()
        s.font_size = self.font_size.value()
        s.show_log = self.show_log.isChecked()
        s.dir_audio, s.dir_video, s.dir_image = self.dir_audio.text(), self.dir_video.text(), self.dir_image.text()
        s.tpl_audio = self.tpl_audio.text().strip() or Settings().tpl_audio
        s.tpl_video = self.tpl_video.text().strip() or Settings().tpl_video
        s.tpl_spotify = self.tpl_spotify.text().strip() or Settings().tpl_spotify
        s.tpl_playlist_folder = self.pl_folder.isChecked()
        s.audio_format = self.audio_format.currentData()
        s.audio_kbps = self.audio_kbps.currentData()
        s.video_res = self.video_res.currentData()
        s.video_fps = self.video_fps.currentData()
        s.video_format = self.video_format.currentData()
        s.embed_thumbnail = self.embed_thumb.isChecked()
        s.embed_metadata = self.embed_meta.isChecked()
        s.subtitles = self.subs.isChecked()
        s.sub_langs = self.sub_langs.text().strip()
        s.auto_start = self.auto_start.isChecked()
        s.cookies_browser = self.browser.currentData()
        s.cookies_file = self.cookies_file.text().strip()
        s.proxy = self.proxy.text().strip()
        s.concurrent = self.concurrent.value()
        s.rate_limit = self.rate.text().strip()
        s.upscale_enabled = self.up_enabled.isChecked()
        s.upscale_factor = self.up_factor.currentData()
        s.upscale_engine = self.up_engine.currentData()
        return s.normalized()
