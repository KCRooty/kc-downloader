"""Herramientas externas: localizar, comprobar versión, instalar y actualizar.

Orden de búsqueda de cada herramienta:
  1. ruta elegida a mano en Ajustes
  2. copia gestionada por la app (carpeta de datos del usuario, se actualiza sola)
  3. copia incluida en la release (carpeta tools/ junto al ejecutable)
  4. PATH del sistema

Solo se descarga de las releases oficiales en GitHub, por HTTPS, y se
comprueba el SHA-256 cuando el proyecto lo publica.

Uso desde línea de órdenes (lo usa el CI para montar la release):
  python -m kcdl.tools status
  python -m kcdl.tools install all --dest <carpeta>
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import net, paths

IS_WINDOWS = paths.IS_WINDOWS
UA = "KC-Downloader (+https://github.com/KCRooty/kc-downloader)"
GH = "https://github.com"

ProgressCb = Callable[[int, int], None]   # (bytes descargados, total o 0)
LogCb = Callable[[str], None]


@dataclass(frozen=True)
class ToolSpec:
    key: str
    label: str
    exe: str            # nombre base del ejecutable
    subdir: str         # subcarpeta dentro de tools/ ("" = raíz)
    required: bool
    purpose: str


TOOLS: dict[str, ToolSpec] = {t.key: t for t in (
    ToolSpec("yt-dlp", "yt-dlp", "yt-dlp", "", True, "Descarga de YouTube, YouTube Music y vídeos de Pinterest"),
    ToolSpec("ffmpeg", "FFmpeg", "ffmpeg", "", True, "Convertir audio, unir vídeo y audio, incrustar carátulas"),
    ToolSpec("deno", "Deno", "deno", "", True, "YouTube lo exige para resolver sus vídeos"),
    ToolSpec("spotdl", "spotDL", "spotdl", "", False, "Álbumes y playlists de Spotify con metadatos completos"),
    ToolSpec("realesrgan", "Real-ESRGAN", "realesrgan-ncnn-vulkan", "realesrgan", False, "Reescalado de imágenes con IA (GPU)"),
)}


def exe_name(base: str) -> str:
    return base + ".exe" if IS_WINDOWS else base


def _arch() -> str:
    m = platform.machine().lower()
    if m in ("aarch64", "arm64"):
        return "arm64"
    return "x64"


def _popen_kw() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}


clean_env = paths.clean_env


# ─── localizar ──────────────────────────────────────────────────────────────

@dataclass
class Found:
    path: Path
    origin: str   # "manual" | "app" | "release" | "sistema"


class ToolManager:
    def __init__(self, overrides: dict | None = None,
                 managed_dir: Path | None = None, bundled_dir: Path | None = None):
        self.overrides = dict(overrides or {})
        self.managed_dir = managed_dir or paths.managed_tools_dir()
        self.bundled_dir = bundled_dir or paths.bundled_tools_dir()

    def _in_dir(self, base: Path, spec: ToolSpec) -> Path | None:
        p = base / spec.subdir / exe_name(spec.exe) if spec.subdir else base / exe_name(spec.exe)
        return p if p.is_file() else None

    def find(self, key: str) -> Found | None:
        spec = TOOLS[key]
        manual = self.overrides.get(key, "").strip()
        if manual and Path(manual).is_file():
            return Found(Path(manual), "manual")
        for base, origin in ((self.managed_dir, "app"), (self.bundled_dir, "release")):
            p = self._in_dir(base, spec)
            if p:
                return Found(p, origin)
        w = shutil.which(spec.exe)
        if w:
            return Found(Path(w), "sistema")
        return None

    def path(self, key: str) -> str | None:
        f = self.find(key)
        return str(f.path) if f else None

    def env(self) -> dict:
        """Entorno para los subprocesos: las carpetas de las herramientas van
        primero en el PATH, así yt-dlp y spotDL encuentran deno y ffmpeg."""
        env = clean_env()
        dirs: list[str] = []
        for key in TOOLS:
            f = self.find(key)
            if f and str(f.path.parent) not in dirs:
                dirs.append(str(f.path.parent))
        env["PATH"] = os.pathsep.join(dirs + [env.get("PATH", "")])
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return env

    def version(self, key: str) -> str | None:
        f = self.find(key)
        if not f:
            return None
        if key == "realesrgan":
            return "instalado"
        args = {"ffmpeg": ["-version"]}.get(key, ["--version"])
        try:
            r = subprocess.run([str(f.path), *args], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=60,
                               env=self.env(), **_popen_kw())
        except (OSError, subprocess.SubprocessError):
            return None
        out = (r.stdout or r.stderr or "").strip().splitlines()
        if r.returncode != 0 or not out:
            return None
        line = out[0].strip()
        if key == "ffmpeg":   # "ffmpeg version N-1234-g... Copyright..."
            parts = line.split()
            return parts[2] if len(parts) > 2 else line
        if key == "deno":     # "deno 2.9.8 (stable, release, ...)"
            parts = line.split()
            return parts[1] if len(parts) > 1 else line
        return line

    def missing_required(self) -> list[str]:
        return [k for k, s in TOOLS.items() if s.required and not self.find(k)]


# ─── descargar ──────────────────────────────────────────────────────────────

def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": UA})


def _get_json(url: str) -> dict:
    with net.urlopen(_request(url), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_text(url: str) -> str:
    with net.urlopen(_request(url), timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _download(url: str, progress: ProgressCb | None) -> bytes:
    with net.urlopen(_request(url), timeout=60) as r:
        total = int(r.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        done = 0
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            buf.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    return buf.getvalue()


def _sha_tokens(line: str) -> list[str]:
    return [t.lower() for t in line.replace("*", " ").split()
            if len(t) == 64 and all(c in "0123456789abcdefABCDEF" for c in t)]


def _check_sha256(data: bytes, sums_text: str, asset: str) -> None:
    """Acepta 'hash  nombre', el formato de Get-FileHash de PowerShell
    (ruta completa) o un fichero con un único hash."""
    want = None
    all_tokens: list[str] = []
    for line in sums_text.splitlines():
        toks = _sha_tokens(line)
        all_tokens += toks
        last = line.split()[-1].lstrip("*") if line.split() else ""
        if toks and (last == asset or last.endswith("/" + asset) or last.endswith("\\" + asset)):
            want = toks[0]
            break
    if not want and len(all_tokens) == 1:
        want = all_tokens[0]
    if not want:
        raise RuntimeError(f"No se encontró el SHA-256 publicado de {asset}")
    got = hashlib.sha256(data).hexdigest()
    if got != want:
        raise RuntimeError(f"SHA-256 no coincide para {asset}: descarga corrupta o alterada")


def _write_exec(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(data)
    if not IS_WINDOWS:
        tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(tmp, dest)


def _plan(key: str) -> dict:
    """URL, nombre del asset y cómo comprobarlo, según sistema y arquitectura."""
    arch = _arch()
    if key == "yt-dlp":
        asset = "yt-dlp.exe" if IS_WINDOWS else ("yt-dlp_linux_aarch64" if arch == "arm64" else "yt-dlp_linux")
        base = f"{GH}/yt-dlp/yt-dlp/releases/latest/download"
        return {"url": f"{base}/{asset}", "asset": asset, "sums": f"{base}/SHA2-256SUMS", "kind": "bin"}
    if key == "ffmpeg":
        tgt = "win64" if IS_WINDOWS else ("linuxarm64" if arch == "arm64" else "linux64")
        asset = f"ffmpeg-master-latest-{tgt}-gpl." + ("zip" if IS_WINDOWS else "tar.xz")
        base = f"{GH}/yt-dlp/FFmpeg-Builds/releases/download/latest"
        return {"url": f"{base}/{asset}", "asset": asset, "sums": f"{base}/checksums.sha256",
                "kind": "archive", "members": ["ffmpeg", "ffprobe"]}
    if key == "deno":
        triple = ("x86_64-pc-windows-msvc" if IS_WINDOWS else
                  ("aarch64-unknown-linux-gnu" if arch == "arm64" else "x86_64-unknown-linux-gnu"))
        asset = f"deno-{triple}.zip"
        base = f"{GH}/denoland/deno/releases/latest/download"
        return {"url": f"{base}/{asset}", "asset": asset, "sums": f"{base}/{asset}.sha256sum",
                "kind": "archive", "members": ["deno"]}
    if key == "spotdl":
        if not IS_WINDOWS and arch == "arm64":
            raise RuntimeError("spotDL no publica binario para Linux ARM64")
        rel = _get_json("https://api.github.com/repos/spotDL/spotify-downloader/releases/latest")
        suffix = "-win32.exe" if IS_WINDOWS else "-linux"
        for a in rel.get("assets", []):
            if a["name"].endswith(suffix):
                return {"url": a["browser_download_url"], "asset": a["name"], "sums": None, "kind": "bin"}
        raise RuntimeError("La última release de spotDL no trae binario para este sistema")
    if key == "realesrgan":
        if arch == "arm64":
            raise RuntimeError("Real-ESRGAN no publica binario para ARM64")
        asset = "realesrgan-ncnn-vulkan-v0.2.0-" + ("windows.zip" if IS_WINDOWS else "ubuntu.zip")
        return {"url": f"{GH}/xinntao/Real-ESRGAN-ncnn-vulkan/releases/download/v0.2.0/{asset}",
                "asset": asset, "sums": None, "kind": "realesrgan"}
    raise KeyError(key)


def _extract_members(data: bytes, asset: str, members: list[str], dest: Path) -> None:
    wanted = {exe_name(m): m for m in members}
    found: set[str] = set()
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                name = info.filename.rsplit("/", 1)[-1]
                if name in wanted and not info.is_dir():
                    _write_exec(dest / name, z.read(info))
                    found.add(name)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as t:
            for m in t.getmembers():
                name = m.name.rsplit("/", 1)[-1]
                if name in wanted and m.isfile():
                    f = t.extractfile(m)
                    if f:
                        _write_exec(dest / name, f.read())
                        found.add(name)
    missing = set(wanted) - found
    if missing:
        raise RuntimeError(f"{asset} no contiene {', '.join(sorted(missing))}")


def _extract_realesrgan(data: bytes, dest: Path) -> None:
    """Copia el ejecutable, sus DLL y la carpeta models/ (descarta los ejemplos)."""
    target = dest / TOOLS["realesrgan"].subdir
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    exe = exe_name("realesrgan-ncnn-vulkan")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            parts = [p for p in info.filename.split("/") if p not in ("", ".", "..")]
            name = parts[-1]
            if "models" in parts:
                out = target / "models" / name
            elif name == exe or name.lower().endswith(".dll"):
                out = target / name
            else:
                continue
            if name == exe:
                _write_exec(out, z.read(info))
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read(info))
    if not (target / exe).is_file():
        raise RuntimeError("El zip de Real-ESRGAN no contiene el ejecutable")


def install(key: str, dest: Path | None = None,
            progress: ProgressCb | None = None, log: LogCb | None = None) -> Path:
    """Descarga e instala (o actualiza) una herramienta en `dest`
    (por defecto, la carpeta gestionada por la app). Devuelve la ruta del ejecutable."""
    dest = dest or paths.managed_tools_dir()
    spec = TOOLS[key]
    say = log or (lambda _m: None)
    plan = _plan(key)
    say(f"Descargando {spec.label}: {plan['asset']}")
    data = _download(plan["url"], progress)
    if plan["sums"]:
        _check_sha256(data, _get_text(plan["sums"]), plan["asset"])
        say(f"SHA-256 de {plan['asset']} comprobado")
    if plan["kind"] == "bin":
        out = dest / exe_name(spec.exe)
        _write_exec(out, data)
    elif plan["kind"] == "archive":
        _extract_members(data, plan["asset"], plan["members"], dest)
        out = dest / exe_name(spec.exe)
    else:
        _extract_realesrgan(data, dest)
        out = dest / spec.subdir / exe_name(spec.exe)
    say(f"{spec.label} instalado en {out}")
    return out


def latest_ytdlp_version() -> str | None:
    try:
        return _get_json("https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest").get("tag_name")
    except Exception:
        return None


# ─── CLI ────────────────────────────────────────────────────────────────────

def _cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m kcdl.tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    ins = sub.add_parser("install")
    ins.add_argument("keys", nargs="+", help="herramientas o 'all'")
    ins.add_argument("--dest", type=Path, default=None)
    a = ap.parse_args(argv)
    if a.cmd == "status":
        tm = ToolManager()
        for k, spec in TOOLS.items():
            f = tm.find(k)
            print(f"{spec.label:12} {'OK ' + (tm.version(k) or '?') if f else 'FALTA':40} "
                  f"{f.origin + ': ' + str(f.path) if f else ''}")
        return 0
    keys = list(TOOLS) if a.keys == ["all"] else a.keys
    for k in keys:
        install(k, a.dest, log=print)
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
