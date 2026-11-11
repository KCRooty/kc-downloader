"""Monta la release: ejecutable (PyInstaller) + herramientas oficiales + archivo comprimido.

  python packaging/build.py              # app + herramientas + zip/tar.gz en dist/
  python packaging/build.py --no-tools   # solo la app (para probar rápido)

Las herramientas se descargan con el mismo código que usa la app
(kcdl.tools.install), con comprobación de SHA-256.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kcdl import __version__, tools  # noqa: E402

IS_WIN = sys.platform.startswith("win")
BUNDLED = ["yt-dlp", "ffmpeg", "deno", "realesrgan"]   # spotDL va aparte: opcional y pesado


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-tools", action="store_true")
    a = ap.parse_args()

    dist = ROOT / "dist"
    app_dir = dist / "KC Downloader"
    if app_dir.exists():
        shutil.rmtree(app_dir)
    subprocess.check_call([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                           "--distpath", str(dist), "--workpath", str(ROOT / "build"),
                           str(ROOT / "packaging" / "kc_downloader.spec")], cwd=ROOT)

    if not a.no_tools:
        dest = app_dir / "tools"
        for key in BUNDLED:
            tools.install(key, dest, log=print)
        tm = tools.ToolManager(managed_dir=dist / "_nada_", bundled_dir=dest)
        for key in BUNDLED:
            f = tm.find(key)
            assert f and f.origin == "release", f"{key} no quedó dentro de la release"
            print(f"{key}: {tm.version(key)}")

    for name in ("README.md", "CHANGELOG.md", "LICENSE"):
        if (ROOT / name).is_file():
            shutil.copy2(ROOT / name, app_dir / name)
    if not IS_WIN:
        shutil.copy2(ROOT / "packaging" / "linux" / "install.sh", app_dir / "install.sh")
        (app_dir / "install.sh").chmod(0o755)

    if IS_WIN:
        out = dist / f"kc-downloader-{__version__}-windows-x64.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for p in sorted(app_dir.rglob("*")):
                z.write(p, Path("KC Downloader") / p.relative_to(app_dir))
    else:
        out = dist / f"kc-downloader-{__version__}-linux-x64.tar.gz"
        with tarfile.open(out, "w:gz") as t:      # tar conserva los permisos de ejecución
            t.add(app_dir, arcname="KC Downloader")
    print(f"Listo: {out} ({out.stat().st_size / 1048576:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
