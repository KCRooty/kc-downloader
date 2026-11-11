"""Ajustes persistentes (JSON en la carpeta de configuración del usuario)."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import paths

AUDIO_FORMATS = ["MP3", "M4A", "OPUS", "OGG", "FLAC", "WAV"]
LOSSLESS_AUDIO = {"FLAC", "WAV"}
AUDIO_KBPS = [128, 192, 256, 320]
VIDEO_RES = ["360p", "480p", "720p", "1080p", "1440p", "4K", "Máxima"]
VIDEO_RES_HEIGHT = {"360p": 360, "480p": 480, "720p": 720, "1080p": 1080,
                    "1440p": 1440, "4K": 2160, "Máxima": None}
VIDEO_FPS = ["Auto", "24", "30", "60"]
VIDEO_FORMATS = ["MP4", "MKV", "WEBM", "MOV"]
MODES = ["audio", "video", "image"]
THEMES = ["system", "dark", "light"]
BROWSERS = ["", "chrome", "firefox", "edge", "brave", "opera", "vivaldi", "chromium"]
UPSCALE_ENGINES = ["Lanczos", "Real-ESRGAN"]

ACCENT_PRESETS = ["#7B61FF", "#3B82F6", "#14B8A6", "#22C55E", "#F59E0B", "#EF4444", "#EC4899"]


def _default_dir(sub: str) -> str:
    return str(paths.default_output_root() / sub)


@dataclass
class Settings:
    # Apariencia
    theme: str = "system"
    accent: str = "#7B61FF"
    font_size: int = 10
    show_log: bool = False

    # Carpetas y nombres de archivo
    dir_audio: str = field(default_factory=lambda: _default_dir("Audio"))
    dir_video: str = field(default_factory=lambda: _default_dir("Vídeo"))
    dir_image: str = field(default_factory=lambda: _default_dir("Imágenes"))
    tpl_audio: str = "%(artist,uploader)s/%(title)s.%(ext)s"
    tpl_video: str = "%(uploader)s/%(title)s.%(ext)s"
    tpl_spotify: str = "{artist}/{title}.{output-ext}"
    tpl_playlist_folder: bool = True

    # Formatos por defecto
    mode: str = "audio"
    audio_format: str = "MP3"
    audio_kbps: int = 320
    video_res: str = "1080p"
    video_fps: str = "Auto"
    video_format: str = "MP4"
    embed_thumbnail: bool = True
    embed_metadata: bool = True
    subtitles: bool = False
    sub_langs: str = "es,en"
    auto_start: bool = False

    # Red y cuentas
    cookies_browser: str = ""
    cookies_file: str = ""
    proxy: str = ""
    concurrent: int = 2
    rate_limit: str = ""

    # Imágenes
    upscale_enabled: bool = False
    upscale_factor: int = 2
    upscale_engine: str = "Lanczos"

    # Herramientas
    auto_update: bool = True
    last_update_check: float = 0.0
    tool_paths: dict = field(default_factory=dict)

    # Estado de ventana
    window_geometry: str = ""

    def output_dir(self, mode: str) -> str:
        return {"audio": self.dir_audio, "video": self.dir_video}.get(mode, self.dir_image)

    def normalized(self) -> "Settings":
        """Corrige valores fuera de rango que pudieran venir de un JSON editado a mano."""
        if self.theme not in THEMES:
            self.theme = "system"
        if self.mode not in MODES:
            self.mode = "audio"
        if self.audio_format not in AUDIO_FORMATS:
            self.audio_format = "MP3"
        if self.audio_kbps not in AUDIO_KBPS:
            self.audio_kbps = 320
        if self.video_res not in VIDEO_RES:
            self.video_res = "1080p"
        if self.video_fps not in VIDEO_FPS:
            self.video_fps = "Auto"
        if self.video_format not in VIDEO_FORMATS:
            self.video_format = "MP4"
        if self.cookies_browser not in BROWSERS:
            self.cookies_browser = ""
        if self.upscale_engine not in UPSCALE_ENGINES:
            self.upscale_engine = "Lanczos"
        if self.upscale_factor not in (2, 3, 4):
            self.upscale_factor = 2
        self.concurrent = max(1, min(int(self.concurrent or 1), 6))
        self.font_size = max(8, min(int(self.font_size or 10), 16))
        if not isinstance(self.tool_paths, dict):
            self.tool_paths = {}
        return self


def settings_file() -> Path:
    return paths.config_dir() / "settings.json"


def load() -> Settings:
    s = Settings()
    f = settings_file()
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return s.normalized()
    if not isinstance(raw, dict):
        return s.normalized()
    for fld in fields(Settings):
        if fld.name not in raw:
            continue
        default = getattr(s, fld.name)
        value = raw[fld.name]
        try:
            if isinstance(default, bool):
                value = bool(value)
            elif isinstance(default, int):
                value = int(value)
            elif isinstance(default, float):
                value = float(value)
            elif isinstance(default, str):
                value = str(value)
            elif isinstance(default, dict) and not isinstance(value, dict):
                continue
        except (TypeError, ValueError):
            continue
        setattr(s, fld.name, value)
    return s.normalized()


def save(s: Settings) -> None:
    f = settings_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(asdict(s), indent=2, ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(dir=f.parent, prefix=".settings-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.replace(tmp, f)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
