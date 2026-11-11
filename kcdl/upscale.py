"""Reescalado de imágenes tras la descarga: Lanczos (Pillow) o Real-ESRGAN (GPU)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from . import paths
from .tools import ToolManager

# Modelos que trae el zip oficial de Real-ESRGAN ncnn-vulkan v0.2.0:
#  - realesrgan-x4plus: fotos, solo x4
#  - realesr-animevideov3: dibujos/ilustración, admite x2, x3 y x4
MODEL_PHOTO_X4 = "realesrgan-x4plus"
MODEL_ANY_SCALE = "realesr-animevideov3"


def _out_path(src: Path, factor: int) -> Path:
    return src.with_name(f"{src.stem}_x{factor}{src.suffix}")


def upscale_file(src: Path, factor: int, engine: str, tm: ToolManager,
                 log: Callable[[str], None]) -> Path | None:
    if engine == "Real-ESRGAN":
        found = tm.find("realesrgan")
        if found:
            out = _out_path(src, factor).with_suffix(".png")
            model = MODEL_PHOTO_X4 if factor == 4 else MODEL_ANY_SCALE
            cmd = [str(found.path), "-i", str(src), "-o", str(out),
                   "-n", model, "-s", str(factor), "-m", str(found.path.parent / "models")]
            kw = {"creationflags": subprocess.CREATE_NO_WINDOW} if paths.IS_WINDOWS else {}
            r = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                               env=tm.env(), **kw)
            if r.returncode == 0 and out.is_file():
                log(f"Real-ESRGAN x{factor}: {out.name}")
                return out
            log(f"Real-ESRGAN falló ({(r.stderr or '').strip()[-200:]}); uso Lanczos")
        else:
            log("Real-ESRGAN no está instalado; uso Lanczos")
    return _lanczos(src, factor, log)


def _lanczos(src: Path, factor: int, log: Callable[[str], None]) -> Path | None:
    try:
        from PIL import Image
    except ImportError:
        log("Pillow no está disponible: no se puede reescalar")
        return None
    out = _out_path(src, factor)
    with Image.open(src) as img:
        w, h = img.size
        up = img.resize((w * factor, h * factor), Image.LANCZOS)
        kw = {"quality": 95, "optimize": True} if src.suffix.lower() in (".jpg", ".jpeg") else {}
        if up.mode in ("RGBA", "P") and src.suffix.lower() in (".jpg", ".jpeg"):
            up = up.convert("RGB")
        up.save(out, **kw)
    log(f"Lanczos x{factor}: {w}×{h} → {w * factor}×{h * factor}")
    return out
