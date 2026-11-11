"""Descargas: modelo de trabajo, órdenes de yt-dlp/spotDL, progreso y ejecución.

No depende de Qt: la UI escucha los eventos que emite `run_job`, y las
pruebas lo usan igual sin abrir ninguna ventana.
"""

from __future__ import annotations

import itertools
import os
import re
import signal
import subprocess
import tempfile
import threading
import urllib.parse
import urllib.request
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import paths
from .config import LOSSLESS_AUDIO, VIDEO_RES_HEIGHT, Settings
from .tools import ToolManager

IS_WINDOWS = paths.IS_WINDOWS
_ids = itertools.count(1)

YTDLP_AUDIO = {"MP3": "mp3", "M4A": "m4a", "OPUS": "opus", "OGG": "vorbis", "FLAC": "flac", "WAV": "wav"}
SPOTDL_AUDIO = {"MP3": "mp3", "M4A": "m4a", "OPUS": "opus", "OGG": "ogg", "FLAC": "flac", "WAV": "wav"}
NO_THUMB_AUDIO = {"WAV"}
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".avif", ".tiff"}

STATUS_LABEL = {"queued": "En cola", "running": "Descargando", "done": "Terminada",
                "error": "Error", "cancelled": "Cancelada"}


@dataclass
class Job:
    url: str
    source: str
    mode: str
    audio_format: str = "MP3"
    audio_kbps: int = 320
    video_res: str = "1080p"
    video_fps: str = "Auto"
    video_format: str = "MP4"
    upscale: bool = False
    id: int = field(default_factory=lambda: next(_ids))
    status: str = "queued"
    title: str = ""
    percent: float = -1.0
    speed: str = ""
    eta: str = ""
    item: str = ""          # "3/12" en playlists
    files: list = field(default_factory=list)
    error: str = ""

    @classmethod
    def from_settings(cls, url: str, source: str, mode: str, s: Settings) -> "Job":
        if source == "pinterest" and mode == "audio":
            mode = "image"
        if source in ("spotify", "ytmusic") and mode == "image":
            mode = "audio"
        if source == "spotify":
            mode = "audio"
        return cls(url=url, source=source, mode=mode,
                   audio_format=s.audio_format, audio_kbps=s.audio_kbps,
                   video_res=s.video_res, video_fps=s.video_fps, video_format=s.video_format,
                   upscale=s.upscale_enabled)

    def quality_label(self) -> str:
        if self.mode == "image":
            return "Imagen original" + (" + reescalado" if self.upscale else "")
        if self.mode == "video":
            fps = "" if self.video_fps == "Auto" else f" {self.video_fps} fps"
            return f"{self.video_res}{fps} · {self.video_format}"
        if self.audio_format in LOSSLESS_AUDIO:
            return self.audio_format
        return f"{self.audio_format} · {self.audio_kbps} kbps"

    def reset(self) -> None:
        self.status, self.percent, self.speed, self.eta, self.item = "queued", -1.0, "", "", ""
        self.files, self.error = [], ""


# ─── órdenes ────────────────────────────────────────────────────────────────

PROG_TAG = "[KCPROG]"
PROGRESS_TEMPLATE = (f"download:{PROG_TAG}%(progress._percent_str)s|"
                     "%(progress._speed_str)s|%(progress._eta_str)s")


def _network_args(s: Settings) -> list[str]:
    a: list[str] = []
    if s.cookies_browser:
        a += ["--cookies-from-browser", s.cookies_browser]
    elif s.cookies_file and Path(s.cookies_file).is_file():
        a += ["--cookies", s.cookies_file]
    if s.proxy.strip():
        a += ["--proxy", s.proxy.strip()]
    if s.rate_limit.strip():
        a += ["--limit-rate", s.rate_limit.strip()]
    return a


def _video_sort(job: Job) -> str:
    keys = []
    h = VIDEO_RES_HEIGHT.get(job.video_res)
    if h:
        keys.append(f"res:{h}")
    if job.video_fps != "Auto":
        keys.append(f"fps:{job.video_fps}")
    if job.video_format in ("MP4", "MOV"):
        keys += ["vcodec:h264", "acodec:aac"]
    elif job.video_format == "WEBM":
        keys += ["vcodec:vp9", "acodec:opus"]
    return ",".join(keys)


def safe_folder(name: str) -> str:
    """Nombre de carpeta válido en Windows y Linux."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", name).strip(" .")
    return name[:120] or "Spotify"


def ytdlp_cmd(job: Job, s: Settings, tm: ToolManager, files_out: Path,
              out_subdir: str = "", search: bool = False) -> list[str]:
    """`search`: la URL es una búsqueda y solo vale el primer resultado."""
    ytdlp = tm.path("yt-dlp") or "yt-dlp"
    ffmpeg = tm.path("ffmpeg")
    out_dir = os.path.join(s.output_dir(job.mode), out_subdir) if out_subdir else s.output_dir(job.mode)
    tpl = s.tpl_audio if job.mode == "audio" else s.tpl_video
    if job.source == "pinterest":
        tpl = "Pinterest/%(title).80s [%(id)s].%(ext)s"
    cmd = [ytdlp, job.url,
           "--newline", "--color", "never", "--no-mtime",
           "--progress-template", PROGRESS_TEMPLATE,
           "--retries", "5", "--fragment-retries", "5",
           "-o", os.path.join(out_dir, tpl),
           "--print-to-file", "after_move:%(filepath)s", str(files_out)]
    if search:
        cmd += ["--playlist-items", "1"]
    elif s.tpl_playlist_folder:
        cmd += ["-o", "pl_video:" + os.path.join(out_dir, "%(playlist_title)s", tpl)]
    if ffmpeg:
        cmd += ["--ffmpeg-location", str(Path(ffmpeg).parent)]
    if job.mode == "audio":
        cmd += ["-f", "ba/b", "-x", "--audio-format", YTDLP_AUDIO[job.audio_format]]
        if job.audio_format not in LOSSLESS_AUDIO:
            cmd += ["--audio-quality", f"{job.audio_kbps}K"]
        if s.embed_thumbnail and job.audio_format not in NO_THUMB_AUDIO:
            cmd += ["--embed-thumbnail"]
    else:
        cmd += ["-f", "bv*+ba/b", "--merge-output-format", job.video_format.lower()]
        sort = _video_sort(job)
        if sort:
            cmd += ["-S", sort]
        if s.embed_thumbnail and job.video_format in ("MP4", "MKV", "MOV"):
            cmd += ["--embed-thumbnail"]
        if s.subtitles and s.sub_langs.strip():
            cmd += ["--write-subs", "--sub-langs", s.sub_langs.strip(), "--embed-subs"]
    if s.embed_metadata:
        cmd += ["--embed-metadata"]
    cmd += _network_args(s)
    return cmd


def spotdl_cmd(job: Job, s: Settings, tm: ToolManager) -> list[str]:
    cmd = [tm.path("spotdl") or "spotdl", "download", job.url,
           "--output", os.path.join(s.dir_audio, s.tpl_spotify),
           "--format", SPOTDL_AUDIO[job.audio_format],
           "--print-errors", "--simple-tui", "--headless"]
    cmd += ["--bitrate", "disable" if job.audio_format in LOSSLESS_AUDIO else f"{job.audio_kbps}k"]
    ffmpeg = tm.path("ffmpeg")
    if ffmpeg:
        cmd += ["--ffmpeg", ffmpeg]
    if s.cookies_file and Path(s.cookies_file).is_file():
        cmd += ["--cookie-file", s.cookies_file]
    if s.proxy.strip():
        cmd += ["--proxy", s.proxy.strip()]
    return cmd


# ─── progreso ───────────────────────────────────────────────────────────────

_PCT = re.compile(r"([\d.]+)\s*%")
_ITEM = re.compile(r"Downloading (?:item|video) (\d+) of (\d+)")
_DEST = re.compile(r"^\[(?:download|ExtractAudio)\] Destination: (.+)$")
_MERGE = re.compile(r'^\[Merger\] Merging formats into "(.+)"$')
_ALREADY = re.compile(r"^\[download\] (.+) has already been downloaded")
_SPOT_DONE = re.compile(r'^(?:Downloaded|Skipping) "(.+?)"')


def parse_line(line: str) -> dict:
    """Traduce una línea de yt-dlp/spotDL a cambios de estado del trabajo."""
    if line.startswith(PROG_TAG):
        pct, _, rest = line[len(PROG_TAG):].partition("|")
        speed, _, eta = rest.partition("|")
        m = _PCT.search(pct)
        upd = {"percent": float(m.group(1))} if m else {}
        speed, eta = speed.strip(), eta.strip()
        upd["speed"] = "" if speed in ("NA", "Unknown B/s", "N/A") else speed
        upd["eta"] = "" if eta in ("NA", "Unknown", "N/A") else eta
        return upd
    m = _ITEM.search(line)
    if m:
        return {"item": f"{m.group(1)}/{m.group(2)}"}
    for rx in (_DEST, _MERGE, _ALREADY):
        m = rx.match(line)
        if m:
            name = re.split(r"[\\/]", m.group(1).strip().strip('"'))[-1]
            stem = name.rsplit(".", 1)[0]
            stem = re.sub(r"\.f\d+$", "", stem)        # quita ".f251" de los formatos sueltos
            return {"title": stem}
    m = _SPOT_DONE.match(line)
    if m:
        return {"title": m.group(1)}
    return {}


def is_error_line(line: str) -> bool:
    return line.startswith("ERROR:") or "AudioProviderError" in line or "LookupError" in line


# ─── ejecución ──────────────────────────────────────────────────────────────

EventCb = Callable[[str, object], None]   # ("log", str) | ("update", dict)


class Cancelled(Exception):
    pass


class Runner:
    """Ejecuta un trabajo. `cancel()` se puede llamar desde otro hilo."""

    def __init__(self, job: Job, s: Settings, tm: ToolManager, emit: EventCb):
        self.job, self.s, self.tm, self.emit = job, s, tm, emit
        self._proc: subprocess.Popen | None = None
        self._cancel = threading.Event()
        self._span = (0, 1)          # (pista actual - 1, total) para el % de un álbum
        self._lock_title = False     # el título lo fija Spotify, no el nombre de archivo

    # -- control
    def cancel(self) -> None:
        self._cancel.set()
        p = self._proc
        if p and p.poll() is None:
            _kill_tree(p)

    def _log(self, msg: str) -> None:
        self.emit("log", msg)

    def _update(self, **kw) -> None:
        for k, v in kw.items():
            setattr(self.job, k, v)
        self.emit("update", kw)

    # -- entrada
    def run(self) -> bool:
        job = self.job
        self._update(status="running", percent=-1.0, error="", files=[])
        try:
            if job.source == "pinterest" and job.mode == "image":
                ok = self._pinterest_image()
            elif job.source == "spotify":
                ok = self._spotify()
            else:
                ok = self._ytdlp()
            if self._cancel.is_set():
                raise Cancelled
            if ok and job.upscale:
                self._upscale()
        except Cancelled:
            self._update(status="cancelled", speed="", eta="")
            self._log(f"Cancelada: {job.url}")
            return False
        except Exception as e:     # nunca dejar el trabajo colgado en "Descargando"
            self._update(status="error", error=str(e), speed="", eta="")
            self._log(f"ERROR: {e}")
            return False
        if ok:
            self._update(status="done", percent=100.0, speed="", eta="")
        else:
            self._update(status="error", speed="", eta="",
                         error=job.error or "La herramienta terminó con error (detalles en el registro)")
        return ok

    # -- yt-dlp
    def _ytdlp(self, as_job: Job | None = None, out_subdir: str = "", search: bool = False) -> bool:
        """`as_job` lanza otra URL (búsqueda de una pista de Spotify) sobre este mismo trabajo;
        los archivos se acumulan en self.job.files."""
        if not self.tm.find("yt-dlp"):
            raise RuntimeError("Falta yt-dlp: instálalo en Ajustes → Herramientas")
        if not self.tm.find("ffmpeg"):
            raise RuntimeError("Falta FFmpeg: instálalo en Ajustes → Herramientas")
        fd, files_out = tempfile.mkstemp(prefix="kcdl-files-", suffix=".txt")
        os.close(fd)
        try:
            ok = self._stream(ytdlp_cmd(as_job or self.job, self.s, self.tm, Path(files_out),
                                        out_subdir=out_subdir, search=search))
            files = [l.strip() for l in Path(files_out).read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        finally:
            try:
                os.unlink(files_out)
            except OSError:
                pass
        if files:
            self._update(files=self.job.files + files)
            if not self.job.title:
                self._update(title=Path(files[0]).stem)
        return ok

    # -- Spotify
    def _spotify(self) -> bool:
        from . import spotify
        try:
            ent = spotify.fetch(self.job.url)
        except Exception as e:
            if self.tm.find("spotdl"):
                self._log(f"No se pudo leer Spotify directamente ({e}); pruebo con spotDL")
                return self._spotdl()
            raise
        n = len(ent.tracks)
        label = ent.name if ent.kind == "track" else f"{ent.name} — {ent.owner}" if ent.owner else ent.name
        self._update(title=label)
        self._lock_title = True
        sub = safe_folder(ent.name) if ent.kind != "track" and self.s.tpl_playlist_folder else ""
        self._log(f"Spotify: {ent.kind} «{ent.name}», {n} pista(s)")
        failed: list[str] = []
        for i, tr in enumerate(ent.tracks, 1):
            if self._cancel.is_set():
                raise Cancelled
            self._span = (i - 1, n)
            if n > 1:
                self._update(item=f"{i}/{n}")
            self._log(f"[{i}/{n}] {tr.query}")
            search = Job(url=spotify.ytmusic_search_url(tr), source="ytmusic", mode="audio",
                         audio_format=self.job.audio_format, audio_kbps=self.job.audio_kbps, id=self.job.id)
            ok = self._ytdlp(as_job=search, out_subdir=sub, search=True)
            if not ok and not self._cancel.is_set():
                self._log("Reintentando la pista (YouTube a veces responde 403 una vez)")
                ok = self._ytdlp(as_job=search, out_subdir=sub, search=True)
            if not ok:
                failed.append(tr.query)
        self._span = (0, 1)
        if failed:
            self.job.error = f"{len(failed)} de {n} pista(s) fallaron: " + "; ".join(failed[:3])
            self._log("ERROR: " + self.job.error)
        return len(failed) < n

    def _spotdl(self) -> bool:
        if not self.tm.find("ffmpeg"):
            raise RuntimeError("Falta FFmpeg: instálalo en Ajustes → Herramientas")
        before = _snapshot(self.s.dir_audio)
        ok = self._stream(spotdl_cmd(self.job, self.s, self.tm))
        new = sorted(_snapshot(self.s.dir_audio) - before)
        if new:
            self._update(files=new)
        return ok and bool(new)

    # -- Pinterest imagen
    def _pinterest_image(self) -> bool:
        out = Path(self.s.dir_image) / "Pinterest"
        out.mkdir(parents=True, exist_ok=True)
        path = pinterest_image(self.job.url, out, self._log)
        self._update(files=[str(path)], title=path.stem)
        return True

    # -- reescalado
    def _upscale(self) -> None:
        from .upscale import upscale_file
        imgs = [f for f in self.job.files if Path(f).suffix.lower() in IMG_EXTS]
        if not imgs:
            return
        self._update(status="running", eta="", speed="reescalando")
        for f in imgs:
            if self._cancel.is_set():
                raise Cancelled
            out = upscale_file(Path(f), self.s.upscale_factor, self.s.upscale_engine, self.tm, self._log)
            if out:
                self.job.files.append(str(out))

    # -- subprocesos
    def _stream(self, cmd: list[str]) -> bool:
        self._log("$ " + " ".join(_q(c) for c in cmd))
        kw: dict = {}
        if IS_WINDOWS:
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            kw["start_new_session"] = True
        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", env=self.tm.env(), **kw)
        last_err = ""
        assert self._proc.stdout is not None
        for raw in self._proc.stdout:
            line = raw.rstrip()
            if not line:
                continue
            upd = parse_line(line)
            if "title" in upd and (self._lock_title or (self.job.title and not self.job.item)):
                upd.pop("title")              # en un vídeo suelto, el primer título es el bueno
            if self._lock_title:
                upd.pop("item", None)         # en Spotify, "i/N" lo lleva el bucle de pistas
            if "percent" in upd:
                done, total = self._span
                upd["percent"] = (done * 100.0 + upd["percent"]) / total
            if upd:
                self._update(**upd)
            if not line.startswith(PROG_TAG):
                self._log(line)
            if is_error_line(line):
                last_err = line.removeprefix("ERROR:").strip()
        rc = self._proc.wait()
        if self._cancel.is_set():
            raise Cancelled
        if rc != 0 and last_err:
            self.job.error = last_err
        return rc == 0


def _q(s: str) -> str:
    return f'"{s}"' if (" " in s or not s) else s


def _kill_tree(p: subprocess.Popen) -> None:
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        try:
            p.kill()
        except OSError:
            pass


def _snapshot(root: str) -> set:
    out = set()
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            out.add(os.path.join(dirpath, f))
    return out


UA_BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


# ─── Pinterest imagen ───────────────────────────────────────────────────────

def pinterest_image(url: str, out_dir: Path, log: Callable[[str], None]) -> Path:
    """Baja la imagen de un pin a la mayor resolución disponible."""
    headers = {"User-Agent": UA_BROWSER, "Accept-Language": "en-US,en;q=0.9"}
    img_url = title = None
    try:
        enc = urllib.parse.quote(url, safe="")
        req = urllib.request.Request(f"https://www.pinterest.com/oembed.json?url={enc}", headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        img_url = data.get("thumbnail_url") or None
        title = data.get("title") or None
    except Exception as e:
        log(f"Pinterest oEmbed no respondió ({e}); probando la página del pin")
    if not img_url:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read(400_000).decode("utf-8", errors="replace")
        for pat in (r'"orig":\{"url":"([^"]+)"', r'<meta property="og:image"\s+content="([^"]+)"',
                    r'"736x":\{"url":"([^"]+)"'):
            m = re.search(pat, html)
            if m:
                img_url = m.group(1).replace("\\u002F", "/").replace("\\/", "/")
                break
    if not img_url:
        raise RuntimeError("No se encontró la imagen del pin (si es un vídeo, usa el modo Vídeo)")

    base = re.sub(r"/(\d+x|originals)/", "/__SIZE__/", img_url)
    candidates = [base.replace("__SIZE__", s) for s in ("originals", "736x", "474x")] + [img_url]
    ext = img_url.split("?")[0].rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp", "gif", "avif"):
        ext = "jpg"
    stem = re.sub(r'[\\/:*?"<>|]+', "_", (title or "pin").strip())[:80] or "pin"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    last_err = ""
    for cand in dict.fromkeys(candidates):
        try:
            req = urllib.request.Request(cand, headers={**headers, "Referer": "https://www.pinterest.com/"})
            with urllib.request.urlopen(req, timeout=30) as r:
                ctype = r.headers.get("Content-Type", "")
                data = r.read()
            if not ctype.startswith("image/"):
                last_err = f"respuesta {ctype or 'sin tipo'}"
                continue
            out = out_dir / f"{stem} {stamp}.{ext}"
            out.write_bytes(data)
            log(f"Pinterest: {out.name} ({len(data) // 1024} KB)")
            return out
        except Exception as e:
            last_err = str(e)
    raise RuntimeError(f"No se pudo bajar la imagen del pin: {last_err}")

