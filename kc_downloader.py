"""
KC Downloader v2.3
Aesthetic: Winamp Classic Dark — early-2000s media player skin
Funcional: yt-dlp auto-update · spotdl para Spotify · Pinterest · upscale post-proceso · thread-safe · retries.
"""

import os
import sys
import subprocess
import threading
import queue
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from dataclasses import dataclass, field
from datetime import datetime

IS_WINDOWS = sys.platform.startswith("win")

# Add exe/script directory to PATH so bundled tools (yt-dlp, ffmpeg, spotdl…) are found
# without the user having to install anything.
_EXE_DIR = (os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))
os.environ["PATH"] = _EXE_DIR + os.pathsep + os.environ.get("PATH", "")

# ─── paleta: media player 2000s (Winamp Classic Dark) ───────────────────────
BG           = "#1e1e1e"    # cuerpo principal (gris hardware)
BG_DISPLAY   = "#060606"    # pantalla VFD (negro puro)
BG_PANEL     = "#2c2c2c"    # paneles
BG_ENTRY     = "#0e0e0e"    # campos de texto
BG_BTN       = "#3d3d3d"    # cara de botones
FG           = "#c4c4c4"    # texto principal
FG_DIM       = "#5a5a5a"    # texto secundario
FG_BTN       = "#e0e0e0"    # texto de botones
PHOSPHOR     = "#00e55c"    # verde VFD fósforo (activo)
PHOSPHOR_DIM = "#005a20"    # verde VFD tenue (idle)
AMBER        = "#FFB000"    # ámbar (descargando / progreso)
GREEN        = "#44cc33"    # OK / listo
RED          = "#cc2222"    # error
BLUE_SEL     = "#1e3888"    # selección en lista
SEP_DARK     = "#0d0d0d"    # separador oscuro (sombra)
SEP_MID      = "#404040"    # separador claro (destaque)

UI_FONT   = "Tahoma"        # THE quintessential XP-era UI font
MONO_FONT = "Lucida Console"

F10   = (UI_FONT,   10)
F10B  = (UI_FONT,   10, "bold")
F9    = (UI_FONT,    9)
F9B   = (UI_FONT,    9, "bold")
F8    = (UI_FONT,    8)
F8B   = (UI_FONT,    8, "bold")
FDSP  = (MONO_FONT, 10)     # pantalla VFD
FMONO = (MONO_FONT,  8)

DEFAULT_OUT = os.path.join(os.path.expanduser("~"), "Downloads", "KC Downloader")

VIDEO_RES_OPTIONS     = ["320p", "720p", "1080p", "4K"]
VIDEO_RES_HEIGHT      = {"320p": 320, "720p": 720, "1080p": 1080, "4K": 2160}
VIDEO_FPS_OPTIONS     = ["Auto", "24", "30", "60"]
VIDEO_FORMAT_OPTIONS  = ["MP4", "MKV", "AVI", "MOV"]
AUDIO_QUALITY_OPTIONS = ["128 kbps", "192 kbps", "256 kbps", "320 kbps (mejor)"]
AUDIO_FORMAT_OPTIONS  = ["MP3", "WAV", "FLAC", "OGG"]
LOSSLESS_FORMATS      = {"WAV", "FLAC"}
YTDLP_FMT   = {"MP3": "mp3", "WAV": "wav", "FLAC": "flac", "OGG": "vorbis"}
SPOTDL_FMT  = {"MP3": "mp3", "WAV": "wav", "FLAC": "flac", "OGG": "ogg"}

UPSCALE_FACTOR_OPTIONS = ["2x", "4x"]
UPSCALE_ENGINE_OPTIONS = ["Lanczos", "Real-ESRGAN"]
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}

_URL_PLACEHOLDER = "Paste URL  —  YouTube / YouTube Music / Spotify / Pinterest"


def audio_kbps(label: str) -> int:
    return int(label.split()[0])


def detect_source(url: str) -> str:
    u = url.lower()
    if "open.spotify.com" in u or u.startswith("spotify:"):
        return "spotify"
    if "music.youtube.com" in u:
        return "ytmusic"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "pinterest.com" in u or "pin.it" in u or "pinterest.es" in u:
        return "pinterest"
    return "desconocido"


def find_tool(name: str) -> str | None:
    return shutil.which(name)


def _popen_kw() -> dict:
    kw = {}
    if IS_WINDOWS:
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


def _lighten(hex_color: str, amt: int = 18) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"#{min(255,r+amt):02x}{min(255,g+amt):02x}{min(255,b+amt):02x}"


def _btn(parent, text: str, command, bg=BG_BTN, fg=FG_BTN,
         font=F10, padx=12, pady=4, **kw) -> tk.Button:
    hover = _lighten(bg)
    b = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg,
        activebackground=hover, activeforeground=fg,
        relief="raised", bd=2,      # efecto físico 2000s
        font=font, padx=padx, pady=pady,
        cursor="hand2", **kw,
    )
    b.bind("<Enter>",            lambda _: b.config(bg=hover))
    b.bind("<Leave>",            lambda _: b.config(bg=bg))
    b.bind("<Button-1>",         lambda _: b.config(relief="sunken"))
    b.bind("<ButtonRelease-1>",  lambda _: b.config(relief="raised"))
    return b


def _hsep(parent, pady=(3, 3)):
    """Separador bevel de dos líneas (sombra + destaque)."""
    tk.Frame(parent, bg=SEP_DARK, height=1).pack(fill="x", padx=6, pady=(pady[0], 0))
    tk.Frame(parent, bg=SEP_MID,  height=1).pack(fill="x", padx=6, pady=(1, pady[1]))


@dataclass
class Item:
    url: str
    source: str
    mode: str
    video_res: str     = "1080p"
    video_fps: str     = "Auto"
    video_format: str  = "MP4"
    audio_quality: str = "320 kbps (mejor)"
    audio_format: str  = "MP3"
    status: str        = "En cola"
    row_id: int        = field(default=-1)


class KCApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("KC Downloader")
        self.geometry("880x640")
        self.minsize(720, 540)
        self.configure(bg=BG)

        self.out_dir       = tk.StringVar(value=DEFAULT_OUT)
        self.mode          = tk.StringVar(value="audio")
        self.video_res     = tk.StringVar(value="1080p")
        self.video_fps     = tk.StringVar(value="Auto")
        self.video_format  = tk.StringVar(value="MP4")
        self.audio_quality = tk.StringVar(value="320 kbps (mejor)")
        self.audio_format  = tk.StringVar(value="MP3")

        self.upscale_enabled = tk.BooleanVar(value=False)
        self.upscale_factor  = tk.StringVar(value="2x")
        self.upscale_engine  = tk.StringVar(value="Lanczos")

        self.items: dict[int, Item] = {}
        self._iids:  dict[int, str] = {}
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.worker_thread: threading.Thread | None = None

        self._setup_styles()
        self._build_ui()
        self.after(150, self._poll_log)
        threading.Thread(target=self._startup_checks, daemon=True).start()

    # ─── TTK styles ────────────────────────────────────────────────────────
    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")

        s.configure("Treeview",
            background=BG_PANEL, foreground=FG,
            fieldbackground=BG_PANEL, borderwidth=0,
            rowheight=24, font=FMONO,
        )
        s.configure("Treeview.Heading",
            background="#282828", foreground=FG_DIM,
            borderwidth=1, relief="raised",
            font=(UI_FONT, 8, "bold"),
        )
        s.map("Treeview",
            background=[("selected", BLUE_SEL)],
            foreground=[("selected", "white")],
        )
        s.map("Treeview.Heading",
            background=[("active", _lighten(BG_PANEL, 10))],
        )
        s.configure("KC.Horizontal.TProgressbar",
            troughcolor="#1a1a1a", background=AMBER,
            bordercolor=SEP_DARK,
            darkcolor=AMBER, lightcolor="#ffc940",
            thickness=7,
        )
        s.configure("Vertical.TScrollbar",
            background=BG_BTN, troughcolor=BG_PANEL,
            bordercolor=SEP_DARK, arrowcolor=FG_DIM,
            relief="raised",
        )
        s.map("Vertical.TScrollbar",
            background=[("active", _lighten(BG_BTN))],
        )

    # ─── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        P = 10

        # ── FILA SUPERIOR (título + estado) ─────────────────────────────
        top = tk.Frame(self, bg="#161616", bd=0)
        top.pack(fill="x")
        inner_top = tk.Frame(top, bg="#161616")
        inner_top.pack(fill="x", padx=2, pady=2)

        tk.Label(inner_top, text="KC DOWNLOADER",
                 bg="#161616", fg=FG, font=F9B,
                 padx=10, pady=3).pack(side="left")
        tk.Label(inner_top, text="YouTube  ·  YouTube Music  ·  Spotify  ·  Pinterest",
                 bg="#161616", fg=FG_DIM, font=F8).pack(side="left", padx=4)

        # status dot + label (esquina derecha)
        self.status_dot = tk.Label(inner_top, text="●", bg="#161616",
                                   fg=GREEN, font=F9)
        self.status_dot.pack(side="right", padx=(0, 8))
        self.status_lbl = tk.Label(inner_top, text="Iniciando...",
                                   bg="#161616", fg=FG_DIM, font=F8)
        self.status_lbl.pack(side="right", padx=(0, 2))

        # ── VFD DISPLAY ──────────────────────────────────────────────────
        # El centrepiece: pantalla negra con texto fósforo verde, como WA
        disp_outer = tk.Frame(self, bg=SEP_DARK)
        disp_outer.pack(fill="x", padx=P, pady=(8, 4))
        disp_inner = tk.Frame(disp_outer, bg=BG_DISPLAY, bd=2, relief="sunken")
        disp_inner.pack(fill="both", padx=1, pady=1)

        vfd_top_row = tk.Frame(disp_inner, bg=BG_DISPLAY)
        vfd_top_row.pack(fill="x")
        tk.Label(vfd_top_row, text="KC DOWNLOADER  v2.3",
                 bg=BG_DISPLAY, fg=PHOSPHOR, font=FDSP,
                 anchor="w", padx=8, pady=4).pack(side="left")
        self.vfd_mode_lbl = tk.Label(vfd_top_row, text="[ IDLE ]",
                 bg=BG_DISPLAY, fg=PHOSPHOR_DIM, font=FDSP,
                 anchor="e", padx=10)
        self.vfd_mode_lbl.pack(side="right")

        # línea divisoria interna (verde oscuro)
        tk.Frame(disp_inner, bg="#001e0a", height=1).pack(fill="x")

        self.vfd_detail = tk.Label(
            disp_inner,
            text=">  Paste a URL above and press  [+ ADD]  to queue a track",
            bg=BG_DISPLAY, fg=PHOSPHOR_DIM, font=FMONO,
            anchor="w", padx=8, pady=4,
        )
        self.vfd_detail.pack(fill="x")

        # ── URL ENTRY ────────────────────────────────────────────────────
        url_row = tk.Frame(self, bg=BG)
        url_row.pack(fill="x", padx=P, pady=(6, 2))

        url_border = tk.Frame(url_row, bg=SEP_DARK, bd=1, relief="sunken")
        url_border.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._url_border = url_border

        self.url_entry = tk.Entry(
            url_border, bg=BG_ENTRY, fg=FG_DIM,
            insertbackground=PHOSPHOR, relief="flat",
            font=FMONO, bd=6,
        )
        self.url_entry.insert(0, _URL_PLACEHOLDER)
        self.url_entry.pack(fill="x", expand=True)
        self.url_entry.bind("<Return>",   lambda _: self._add_item())
        self.url_entry.bind("<FocusIn>",  self._url_focus_in)
        self.url_entry.bind("<FocusOut>", self._url_focus_out)

        _btn(url_row, "+ ADD", self._add_item,
             bg="#1c3a1c", fg="#8aff8a",
             font=F10B, padx=18, pady=5,
        ).pack(side="left")

        # ── OPCIONES ─────────────────────────────────────────────────────
        opts = tk.Frame(self, bg=BG)
        opts.pack(fill="x", padx=P, pady=(4, 0))

        tk.Label(opts, text="MODE:", bg=BG, fg=FG_DIM, font=F8B).pack(side="left")
        for lbl, val in (("Audio", "audio"), ("Video", "video"), ("Image", "image")):
            tk.Radiobutton(
                opts, text=lbl, variable=self.mode, value=val,
                bg=BG, fg=FG, selectcolor="#2a2a2a",
                activebackground=BG, activeforeground=AMBER,
                font=F9, cursor="hand2",
            ).pack(side="left", padx=(5, 0))

        tk.Frame(opts, bg=SEP_DARK, width=2).pack(
            side="left", fill="y", padx=10, pady=2)

        tk.Label(opts, text="AUDIO:", bg=BG, fg=FG_DIM, font=F8B).pack(side="left")
        self._omenu(opts, self.audio_quality, AUDIO_QUALITY_OPTIONS).pack(side="left", padx=(4, 0))
        self._omenu(opts, self.audio_format,  AUDIO_FORMAT_OPTIONS).pack(side="left", padx=(3, 0))

        tk.Frame(opts, bg=SEP_DARK, width=2).pack(
            side="left", fill="y", padx=10, pady=2)

        tk.Label(opts, text="VIDEO:", bg=BG, fg=FG_DIM, font=F8B).pack(side="left")
        self._omenu(opts, self.video_res,    VIDEO_RES_OPTIONS).pack(side="left", padx=(4, 0))
        self._omenu(opts, self.video_fps,    VIDEO_FPS_OPTIONS).pack(side="left", padx=(3, 0))
        self._omenu(opts, self.video_format, VIDEO_FORMAT_OPTIONS).pack(side="left", padx=(3, 0))

        # fila carpeta + botón update
        dir_row = tk.Frame(self, bg=BG)
        dir_row.pack(fill="x", padx=P, pady=(3, 5))
        tk.Label(dir_row, text="SAVE TO:", bg=BG, fg=FG_DIM, font=F8B).pack(side="left")
        tk.Label(dir_row, textvariable=self.out_dir, bg=BG, fg=FG_DIM,
                 font=(MONO_FONT, 8)).pack(side="left", padx=(5, 10))
        _btn(dir_row, "Browse...", self._choose_dir,
             bg=BG_BTN, font=F8, padx=8, pady=1).pack(side="left")
        self.update_btn = _btn(
            dir_row, "↻ yt-dlp", self._manual_update_ytdlp,
            bg=BG_BTN, font=F8, padx=8, pady=1,
        )
        self.update_btn.pack(side="right")

        # fila upscale
        up_row = tk.Frame(self, bg=BG)
        up_row.pack(fill="x", padx=P, pady=(0, 4))
        tk.Checkbutton(
            up_row, text="UPSCALE IMGS:", variable=self.upscale_enabled,
            bg=BG, fg=FG_DIM, selectcolor="#2a2a2a",
            activebackground=BG, activeforeground=AMBER,
            font=F8B, cursor="hand2",
        ).pack(side="left")
        self._omenu(up_row, self.upscale_factor, UPSCALE_FACTOR_OPTIONS).pack(
            side="left", padx=(4, 0))
        self._omenu(up_row, self.upscale_engine, UPSCALE_ENGINE_OPTIONS).pack(
            side="left", padx=(3, 0))
        tk.Label(up_row,
                 text="— aplica tras la descarga  (Real-ESRGAN: ultrasharp-4x/upscayl-lite-4x, GPU RTX)",
                 bg=BG, fg=FG_DIM, font=F8).pack(side="left", padx=(8, 0))

        _hsep(self)

        # ── COLA (Treeview) ──────────────────────────────────────────────
        tree_outer = tk.Frame(self, bg=SEP_DARK, bd=1, relief="sunken")
        tree_outer.pack(fill="both", expand=True, padx=P, pady=(2, 4))
        tree_inner = tk.Frame(tree_outer, bg=BG_PANEL)
        tree_inner.pack(fill="both", expand=True, padx=1, pady=1)

        cols = ("source", "mode", "quality", "status", "url")
        self.tree = ttk.Treeview(tree_inner, columns=cols,
                                  show="headings", selectmode="browse")
        col_cfg = [
            ("source",  "SOURCE",   80,  False),
            ("mode",    "TYPE",     62,  False),
            ("quality", "QUALITY",  100, False),
            ("status",  "STATUS",   112, False),
            ("url",     "URL",      410, True),
        ]
        for cid, text, w, stretch in col_cfg:
            self.tree.heading(cid, text=text)
            self.tree.column(cid, width=w, minwidth=40, stretch=stretch)

        self.tree.tag_configure("queued",      foreground=FG_DIM)
        self.tree.tag_configure("downloading", foreground=AMBER)
        self.tree.tag_configure("ok",          foreground=GREEN)
        self.tree.tag_configure("error",       foreground=RED)

        vsb = ttk.Scrollbar(tree_inner, orient="vertical",
                             command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # ── CONTROLES ────────────────────────────────────────────────────
        _hsep(self, pady=(0, 0))
        ctrl = tk.Frame(self, bg=BG)
        ctrl.pack(fill="x", padx=P, pady=6)

        self.download_btn = _btn(
            ctrl, "▶  DOWNLOAD", self._start_download,
            bg="#1c3a1c", fg="#8aff8a",
            font=F10B, padx=22, pady=6,
        )
        self.download_btn.pack(side="left")
        _btn(ctrl, "✕ Remove", self._remove_selected,
             bg=BG_BTN, font=F9, padx=10).pack(side="left", padx=6)
        _btn(ctrl, "⊘ Clear", self._clear_queue,
             bg=BG_BTN, font=F9, padx=10).pack(side="left")
        _btn(ctrl, "📁 Open Folder", self._open_out_dir,
             bg=BG_BTN, fg=AMBER, font=F9, padx=10).pack(side="right")

        # barra de progreso ámbar
        self.progress = ttk.Progressbar(
            self, style="KC.Horizontal.TProgressbar",
            mode="indeterminate",
        )
        self.progress.pack(fill="x", padx=P, pady=(0, 3))

        _hsep(self, pady=(0, 0))

        # ── LOG (fondo negro, texto fósforo) ─────────────────────────────
        log_outer = tk.Frame(self, bg=SEP_DARK, bd=1, relief="sunken")
        log_outer.pack(fill="both", padx=P, pady=(4, P))

        log_hdr = tk.Frame(log_outer, bg="#161616")
        log_hdr.pack(fill="x")
        tk.Label(log_hdr, text=" OUTPUT LOG",
                 bg="#161616", fg=FG_DIM,
                 font=F8B, anchor="w").pack(fill="x", padx=4, pady=2)

        self.log_text = tk.Text(
            log_outer, height=6,
            bg=BG_DISPLAY, fg=PHOSPHOR_DIM,
            relief="flat", font=FMONO,
            state="disabled",
            selectbackground=BLUE_SEL,
            padx=8, pady=4,
        )
        self.log_text.pack(fill="both", expand=True)

        self.log_text.tag_configure("ts",       foreground="#002a10")
        self.log_text.tag_configure("ok",       foreground=GREEN)
        self.log_text.tag_configure("err",      foreground=RED)
        self.log_text.tag_configure("warn",     foreground=AMBER)
        self.log_text.tag_configure("progress", foreground=PHOSPHOR)
        self.log_text.tag_configure("dim",      foreground=PHOSPHOR_DIM)

    # ─── helpers ──────────────────────────────────────────────────────────
    def _omenu(self, parent, var, options) -> tk.OptionMenu:
        om = tk.OptionMenu(parent, var, *options)
        om.config(
            bg=BG_BTN, fg=FG,
            activebackground=_lighten(BG_BTN),
            activeforeground=FG,
            relief="raised", bd=2,
            font=F9, highlightthickness=0,
            padx=4, pady=2, cursor="hand2",
        )
        om["menu"].config(
            bg=BG_PANEL, fg=FG,
            activebackground=BLUE_SEL, activeforeground="white",
            font=F9,
        )
        return om

    def _url_focus_in(self, _=None):
        self._url_border.config(bg=PHOSPHOR_DIM)
        if self.url_entry.get() == _URL_PLACEHOLDER:
            self.url_entry.delete(0, "end")
            self.url_entry.config(fg=FG)

    def _url_focus_out(self, _=None):
        self._url_border.config(bg=SEP_DARK)
        if not self.url_entry.get():
            self.url_entry.insert(0, _URL_PLACEHOLDER)
            self.url_entry.config(fg=FG_DIM)

    def _get_url(self) -> str:
        v = self.url_entry.get().strip()
        return "" if v == _URL_PLACEHOLDER else v

    # ─── acciones ─────────────────────────────────────────────────────────
    def _choose_dir(self):
        d = filedialog.askdirectory(
            initialdir=self.out_dir.get() or os.path.expanduser("~"))
        if d:
            self.out_dir.set(d)

    def _open_out_dir(self):
        d = self.out_dir.get()
        os.makedirs(d, exist_ok=True)
        if IS_WINDOWS:
            os.startfile(d)
        else:
            subprocess.Popen(["xdg-open", d])

    def _add_item(self):
        url = self._get_url()
        if not url:
            return
        source = detect_source(url)
        if source == "desconocido":
            messagebox.showwarning("URL no reconocida",
                "No parece un link de YouTube, YouTube Music, Spotify o Pinterest.")
            return
        if source == "pinterest" and self.mode.get() not in ("image", "video"):
            self.mode.set("image")
        item = Item(
            url=url, source=source, mode=self.mode.get(),
            video_res=self.video_res.get(), video_fps=self.video_fps.get(),
            video_format=self.video_format.get(),
            audio_quality=self.audio_quality.get(),
            audio_format=self.audio_format.get(),
        )
        idx = len(self.items)
        self.items[idx] = item
        self._iids[idx] = self._insert_row(idx)
        self.url_entry.delete(0, "end")

    def _quality_str(self, item: Item) -> str:
        if item.mode == "image":
            return "Original"
        if item.mode == "video":
            return f"{item.video_res} {item.video_format}"
        if item.audio_format in LOSSLESS_FORMATS:
            return item.audio_format
        return f"{audio_kbps(item.audio_quality)}k {item.audio_format}"

    def _status_tag(self, status: str) -> str:
        return {"En cola": "queued", "Descargando": "downloading",
                "OK": "ok", "Error": "error"}.get(status, "queued")

    def _status_label(self, status: str) -> str:
        return {"En cola": "⋯ En cola", "Descargando": "⬇ Descargando",
                "OK": "✓ OK", "Error": "✗ Error"}.get(status, status)

    def _insert_row(self, idx: int) -> str:
        item = self.items[idx]
        iid = self.tree.insert("", "end",
            values=(item.source, item.mode,
                    self._quality_str(item),
                    self._status_label(item.status),
                    item.url),
            tags=(self._status_tag(item.status),),
        )
        return iid

    def _refresh_row(self, idx: int):
        item = self.items[idx]
        iid  = self._iids.get(idx)
        if iid and self.tree.exists(iid):
            self.tree.item(iid,
                values=(item.source, item.mode,
                        self._quality_str(item),
                        self._status_label(item.status),
                        item.url),
                tags=(self._status_tag(item.status),),
            )

    def _remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        target = next((i for i, v in self._iids.items() if v == iid), None)
        if target is None:
            return
        self.tree.delete(iid)
        del self.items[target]
        del self._iids[target]
        new_items, new_iids = {}, {}
        for new_i, (old_i, item) in enumerate(sorted(self.items.items())):
            new_items[new_i] = item
            new_iids[new_i]  = self._iids.get(old_i, "")
        self.items, self._iids = new_items, new_iids

    def _clear_queue(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("En curso", "Espera a que termine la descarga.")
            return
        self.items.clear()
        self._iids.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)

    # ─── log + VFD ────────────────────────────────────────────────────────
    def _log(self, msg: str):
        self.log_queue.put(msg)

    def _log_tag(self, msg: str) -> str:
        if "✓" in msg or "al día" in msg or msg[:2] == "OK":
            return "ok"
        if "✗" in msg or "Error" in msg or "FALLO" in msg:
            return "err"
        if "⚠" in msg:
            return "warn"
        if "[download]" in msg or ("%" in msg and "ETA" in msg):
            return "progress"
        return "dim"

    def _poll_log(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                ts  = f"[{datetime.now().strftime('%H:%M:%S')}] "
                tag = self._log_tag(msg)
                self.log_text.config(state="normal")
                self.log_text.insert("end", ts, "ts")
                self.log_text.insert("end", msg + "\n", tag)
                self.log_text.see("end")
                self.log_text.config(state="disabled")
                # refleja el último mensaje en el display VFD
                short = (msg[:72] + "...") if len(msg) > 72 else msg
                self.vfd_detail.config(text=f">  {short}")
        except queue.Empty:
            pass
        self.after(150, self._poll_log)

    def _set_status(self, dot: str, text: str):
        def _apply():
            self.status_dot.config(fg=dot)
            self.status_lbl.config(text=text)
            if dot == GREEN:
                self.vfd_mode_lbl.config(text="[ READY ]",       fg=PHOSPHOR)
            elif dot == AMBER:
                self.vfd_mode_lbl.config(text="[ DOWNLOADING ]", fg=AMBER)
            elif dot == RED:
                self.vfd_mode_lbl.config(text="[ ERROR ]",       fg=RED)
        self.after(0, _apply)

    # ─── descarga ─────────────────────────────────────────────────────────
    def _start_download(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("En curso", "Ya hay una descarga en marcha.")
            return
        if not self.items:
            messagebox.showinfo("Cola vacía", "Añade al menos una URL.")
            return
        os.makedirs(self.out_dir.get(), exist_ok=True)
        self.worker_thread = threading.Thread(
            target=self._download_worker, daemon=True)
        self.worker_thread.start()

    def _download_worker(self):
        self.after(0, lambda: self.download_btn.config(
            state="disabled", text="⏸  DOWNLOADING...",
            bg="#3a3a0a", fg=AMBER))
        self.after(0, self.progress.start, 10)
        self._set_status(AMBER, "Descargando...")

        errors = 0
        for idx in sorted(self.items):
            item = self.items[idx]
            if item.status == "OK":
                continue
            before_imgs = (self._snapshot_images(self.out_dir.get())
                           if self.upscale_enabled.get() else set())
            item.status = "Descargando"
            self.after(0, self._refresh_row, idx)
            self._log(f"▶ [{item.source}] {item.url}")
            try:
                ok = self._run_download(item)
                item.status = "OK" if ok else "Error"
                if not ok:
                    errors += 1
                elif self.upscale_enabled.get():
                    after_imgs = self._snapshot_images(self.out_dir.get())
                    new_imgs = list(after_imgs - before_imgs)
                    if new_imgs:
                        self._post_upscale(new_imgs)
            except Exception as e:
                item.status = "Error"
                errors += 1
                self._log(f"✗ Excepción: {e}")
            self.after(0, self._refresh_row, idx)
            self._log(f"{'✓ OK' if item.status == 'OK' else '✗ FALLO'}: {item.url}")

        self._log("Cola completada.")
        self.after(0, self.progress.stop)
        self.after(0, lambda: self.download_btn.config(
            state="normal", text="▶  DOWNLOAD",
            bg="#1c3a1c", fg="#8aff8a"))
        self._set_status(RED if errors else GREEN,
                         f"{errors} error(es)" if errors else "Listo")

    # ─── startup checks / update ──────────────────────────────────────────
    def _startup_checks(self):
        missing = [t for t in ("yt-dlp", "spotdl", "ffmpeg") if not find_tool(t)]
        if missing:
            self._log(f"⚠ No encontradas en PATH: {', '.join(missing)}")
            self._log("  → pip install yt-dlp spotdl  +  ffmpeg en PATH")
            self._set_status(RED, "Herramientas faltantes")
        else:
            self._log("✓ yt-dlp · spotdl · ffmpeg — OK")
            self._auto_update_ytdlp()

    def _auto_update_ytdlp(self):
        self._log("Comprobando actualizaciones de yt-dlp...")
        try:
            result = subprocess.run(
                ["yt-dlp", "-U"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                **_popen_kw(),
            )
            lines = [l for l in (result.stdout + result.stderr).splitlines() if l.strip()]
            msg   = lines[-1] if lines else "(sin salida)"
            if "up to date" in msg.lower() or "latest version" in msg.lower():
                self._log(f"✓ yt-dlp al día — {msg}")
            else:
                self._log(f"✓ yt-dlp: {msg}")
            self._set_status(GREEN, "Listo")
        except Exception as e:
            self._log(f"⚠ yt-dlp -U: {e}")
            self._set_status(GREEN, "Listo")

    def _manual_update_ytdlp(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("En curso", "Espera a que termine la descarga.")
            return
        self.after(0, lambda: self.update_btn.config(
            state="disabled", text="Actualizando..."))
        def _do():
            self._auto_update_ytdlp()
            self.after(0, lambda: self.update_btn.config(
                state="normal", text="↻ yt-dlp"))
        threading.Thread(target=_do, daemon=True).start()

    # ─── core ─────────────────────────────────────────────────────────────
    def _run_download(self, item: Item) -> bool:
        out_dir = self.out_dir.get()
        if item.source == "pinterest":
            return self._download_pinterest(item, out_dir)
        if item.source == "spotify":
            return self._download_spotify(item, out_dir)
        return self._download_youtube(item, out_dir)

    def _download_spotify(self, item: Item, out_dir: str) -> bool:
        """Obtiene título de Spotify sin auth y descarga desde YouTube.
        Fallback a spotdl si falla la extracción de metadata."""
        import urllib.request, urllib.parse, json as _json, re as _re

        search_query = None

        # intento 1: oembed público (no requiere auth)
        try:
            enc = urllib.parse.quote(item.url, safe="")
            req = urllib.request.Request(
                f"https://open.spotify.com/oembed?url={enc}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=8) as r:
                data = _json.loads(r.read())
            title = data.get("title", "").strip()
            if title:
                search_query = title
                self._log(f"⟳ Spotify: {title}")
        except Exception:
            pass

        # intento 2: og:title de la página (formato "Track - Artist | Spotify")
        if not search_query:
            try:
                req = urllib.request.Request(
                    item.url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                )
                with urllib.request.urlopen(req, timeout=10) as r:
                    html = r.read(65536).decode("utf-8", errors="replace")
                m = _re.search(r'<meta property="og:title"\s+content="([^"]+)"', html)
                if m:
                    raw = m.group(1).split(" | ")[0].strip()
                    if raw:
                        search_query = raw
                        self._log(f"⟳ Spotify og:title: {raw}")
            except Exception:
                pass

        # si tenemos el título → buscar en YouTube con yt-dlp
        if search_query:
            self._log(f"⟳ Buscando en YouTube: {search_query}")
            return self._download_yt_search(search_query, item, out_dir)

        # fallback: spotdl directo
        self._log("⚠ Sin metadata, intentando spotdl...")
        return self._download_spotify_spotdl(item, out_dir)

    def _download_yt_search(self, query: str, item: Item, out_dir: str) -> bool:
        """Busca en YouTube y descarga el primer resultado."""
        if not find_tool("yt-dlp"):
            self._log("✗ yt-dlp no instalado")
            return False
        out_tpl = os.path.join(out_dir, "%(uploader)s", "%(title)s.%(ext)s")
        cmd = [
            "yt-dlp", f"ytsearch1:{query}",
            "--newline", "-x",
            "--audio-format", YTDLP_FMT[item.audio_format],
            "--embed-thumbnail", "--add-metadata",
            "--retries", "5", "--fragment-retries", "5",
            "-o", out_tpl,
        ]
        if item.audio_format not in LOSSLESS_FORMATS:
            cmd += ["--audio-quality", f"{audio_kbps(item.audio_quality)}K"]
        return self._stream_cmd(cmd)

    def _download_spotify_spotdl(self, item: Item, out_dir: str) -> bool:
        """Fallback: usa spotdl si la extracción de metadata falló."""
        if not find_tool("spotdl"):
            self._log("✗ spotdl no instalado — pip install spotdl")
            return False
        fmt = SPOTDL_FMT[item.audio_format]
        output_tpl = os.path.join(out_dir, "{artist}", "{title}.{output-ext}")
        cmd = ["spotdl", "download", item.url,
               "--output", output_tpl, "--format", fmt]
        if item.audio_format not in LOSSLESS_FORMATS:
            cmd += ["--bitrate", f"{audio_kbps(item.audio_quality)}k"]
        return self._stream_cmd(cmd)

    def _download_youtube(self, item: Item, out_dir: str) -> bool:
        if not find_tool("yt-dlp"):
            self._log("✗ yt-dlp no instalado — pip install yt-dlp")
            return False
        out_tpl = os.path.join(out_dir, "%(uploader)s", "%(title)s.%(ext)s")
        if item.mode == "audio":
            cmd = [
                "yt-dlp", item.url,
                "--newline", "-x",
                "--audio-format", YTDLP_FMT[item.audio_format],
                "--embed-thumbnail", "--add-metadata",
                "--retries", "5", "--fragment-retries", "5",
                "-o", out_tpl,
            ]
            if item.audio_format not in LOSSLESS_FORMATS:
                cmd += ["--audio-quality", f"{audio_kbps(item.audio_quality)}K"]
        else:
            height = VIDEO_RES_HEIGHT[item.video_res]
            fps_f  = "" if item.video_fps == "Auto" else f"[fps<={item.video_fps}]"
            fmt_s  = (f"bestvideo[height<={height}]{fps_f}"
                      f"+bestaudio/best[height<={height}]")
            cmd = [
                "yt-dlp", item.url,
                "--newline", "-f", fmt_s,
                "--merge-output-format", item.video_format.lower(),
                "--retries", "5", "--fragment-retries", "5",
                "-o", out_tpl,
            ]
        return self._stream_cmd(cmd)

    def _stream_cmd(self, cmd: list) -> bool:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            **_popen_kw(),
        )
        thumbnail_err = False
        real_err      = False
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                self._log(line)
                if "WinError 32" in line and (".temp." in line or "thumbnail" in line.lower()):
                    thumbnail_err = True
                elif line.startswith("ERROR:") and "WinError 32" not in line:
                    real_err = True
        proc.wait()
        # WinError 32 en el thumbnail es un falso fallo: Windows Defender/Preview
        # bloquea el .temp momentáneamente — el audio ya está en disco.
        if proc.returncode != 0 and thumbnail_err and not real_err:
            self._log("⚠ Thumbnail no embebido (archivo bloqueado por Windows) — audio OK")
            return True
        return proc.returncode == 0


    # ─── pinterest ────────────────────────────────────────────────────────
    def _download_pinterest(self, item: Item, out_dir: str) -> bool:
        sub = os.path.join(out_dir, "Pinterest")
        os.makedirs(sub, exist_ok=True)
        if item.mode == "video":
            if not find_tool("yt-dlp"):
                self._log("✗ yt-dlp no instalado")
                return False
            height = VIDEO_RES_HEIGHT[item.video_res]
            fps_f  = "" if item.video_fps == "Auto" else f"[fps<={item.video_fps}]"
            fmt_s  = f"bestvideo[height<={height}]{fps_f}+bestaudio/best[height<={height}]"
            out_tpl = os.path.join(sub, "%(title)s.%(ext)s")
            cmd = [
                "yt-dlp", item.url, "--newline",
                "-f", fmt_s,
                "--merge-output-format", item.video_format.lower(),
                "--retries", "5", "-o", out_tpl,
            ]
            return self._stream_cmd(cmd)
        else:
            return self._download_pinterest_image(item, sub)

    def _download_pinterest_image(self, item: Item, sub_dir: str) -> bool:
        import urllib.request, urllib.parse, json as _json, re as _re
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")

        img_url = None

        # Método 1: oembed API — no requiere cookies ni JS, funciona en España/GDPR
        try:
            enc = urllib.parse.quote(item.url, safe="")
            req = urllib.request.Request(
                f"https://www.pinterest.com/oembed.json?url={enc}",
                headers={"User-Agent": ua},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                data = _json.loads(r.read())
            thumb = data.get("thumbnail_url", "")
            if thumb:
                img_url = thumb
                self._log(f"⟳ Pinterest oembed OK: {data.get('title', '')[:50]}")
        except Exception as e:
            self._log(f"⚠ oembed falló: {e}")

        # Método 2: og:image del HTML (fallback — puede fallar con consent wall GDPR)
        if not img_url:
            try:
                req = urllib.request.Request(
                    item.url,
                    headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"},
                )
                with urllib.request.urlopen(req, timeout=15) as r:
                    html = r.read(196608).decode("utf-8", errors="replace")
                for pat in [
                    r'"orig":\{"url":"([^"]+)"',
                    r'<meta property="og:image"\s+content="([^"]+)"',
                    r'"736x":\{"url":"([^"]+)"',
                ]:
                    m = _re.search(pat, html)
                    if m:
                        img_url = m.group(1).replace("\\u002F", "/").replace("\\/", "/")
                        self._log(f"⟳ Pinterest HTML scrape OK")
                        break
            except Exception as e:
                self._log(f"⚠ HTML scrape falló: {e}")

        if not img_url:
            self._log("✗ No se pudo obtener URL de imagen — si es un video pin usa modo Video")
            return False

        # Construir candidatos de calidad en orden descendente
        base = _re.sub(r'/(236x|474x|736x|564x|1200x|\d+x|originals)/', '/__SIZE__/', img_url)
        candidates = [
            (_re.sub(r'/__SIZE__/', '/originals/', base), "originals"),
            (_re.sub(r'/__SIZE__/', '/736x/',     base), "736x"),
            (_re.sub(r'/__SIZE__/', '/474x/',     base), "474x"),
            (img_url,                                    "oembed"),
        ]

        raw_name_base = img_url.split("?")[0].rsplit("/", 1)[-1]
        ext = raw_name_base.rsplit(".", 1)[-1] if "." in raw_name_base else "jpg"
        if ext not in ("jpg", "jpeg", "png", "webp", "gif", "avif"):
            ext = "jpg"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        for url_try, label in candidates:
            try:
                req2 = urllib.request.Request(
                    url_try,
                    headers={"User-Agent": ua, "Referer": "https://www.pinterest.com/"},
                )
                with urllib.request.urlopen(req2, timeout=20) as r:
                    content_type = r.headers.get("Content-Type", "")
                    raw_bytes = r.read()

                # Pinterest puede devolver HTML (consent/error) en vez de imagen
                if not content_type.startswith("image/"):
                    self._log(f"⚠ [{label}] devolvió {content_type[:30]}, no es imagen")
                    continue

                fname = f"pin_{ts}_{label}.{ext}"
                out_path = os.path.join(sub_dir, fname)
                with open(out_path, "wb") as f:
                    f.write(raw_bytes)
                size_kb = len(raw_bytes) / 1024
                self._log(f"✓ Pinterest [{label}]: {fname}  ({size_kb:.0f} KB)")
                return True
            except Exception as e:
                self._log(f"⚠ [{label}] falló: {e}")
                continue

        return False

    # ─── upscale post-proceso ─────────────────────────────────────────────
    def _snapshot_images(self, path: str) -> set:
        result = set()
        if not os.path.isdir(path):
            return result
        for root, _, files in os.walk(path):
            for f in files:
                if os.path.splitext(f)[1].lower() in IMG_EXTS:
                    result.add(os.path.join(root, f))
        return result

    def _post_upscale(self, new_images: list):
        factor = int(self.upscale_factor.get()[0])  # "2x" → 2
        engine = self.upscale_engine.get()
        self._log(f"⟳ Upscaling {len(new_images)} imagen(es) — {factor}x {engine}")
        for path in new_images:
            self._upscale_file(path, factor, engine)
        self._log(f"✓ Upscale completado ({len(new_images)} imagen(es))")

    def _upscale_file(self, path: str, factor: int, engine: str):
        import shutil as _shutil
        fname = os.path.basename(path)
        if engine == "Real-ESRGAN" and find_tool("realesrgan-ncnn-vulkan"):
            exe = _shutil.which("realesrgan-ncnn-vulkan")
            models_dir = os.path.join(os.path.dirname(exe), "models") if exe else "models"
            model = "ultrasharp-4x" if factor >= 4 else "upscayl-lite-4x"
            base, ext = os.path.splitext(path)
            out_path = f"{base}_x{factor}{ext}"
            cmd = [
                "realesrgan-ncnn-vulkan",
                "-i", path, "-o", out_path,
                "-m", models_dir, "-n", model, "-s", str(factor),
            ]
            r = subprocess.run(cmd, capture_output=True, **_popen_kw())
            if r.returncode == 0:
                self._log(f"✓ ESRGAN: {fname} → x{factor}")
            else:
                self._log(f"⚠ ESRGAN falló en {fname}, usando Lanczos")
                self._upscale_lanczos(path, factor)
        else:
            if engine == "Real-ESRGAN":
                self._log("⚠ realesrgan-ncnn-vulkan no en PATH → usando Lanczos")
            self._upscale_lanczos(path, factor)

    def _upscale_lanczos(self, path: str, factor: int):
        try:
            from PIL import Image
        except ImportError:
            self._log("⚠ Pillow no instalado — pip install Pillow")
            return
        try:
            img = Image.open(path)
            w, h = img.size
            up = img.resize((w * factor, h * factor), Image.LANCZOS)
            base, ext = os.path.splitext(path)
            out_path = f"{base}_x{factor}{ext}"
            save_kw = ({"quality": 95, "optimize": True}
                       if ext.lower() in {".jpg", ".jpeg"} else {})
            up.save(out_path, **save_kw)
            self._log(f"✓ Lanczos: {os.path.basename(path)} {w}×{h} → {w*factor}×{h*factor}")
        except Exception as e:
            self._log(f"✗ Upscale: {os.path.basename(path)}: {e}")


if __name__ == "__main__":
    app = KCApp()
    app.mainloop()
