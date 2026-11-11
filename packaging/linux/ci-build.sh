#!/usr/bin/env bash
# Build de Linux dentro de python:3.12-slim-bookworm (Debian 12, glibc 2.36).
# Paquetes de deb.debian.org, no de los mirrors de Ubuntu de los runners.
# Uso (desde la raíz del repo): docker run --rm -v "$PWD:/src" -w /src python:3.12-slim-bookworm bash packaging/linux/ci-build.sh
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
APT="-o Acquire::Retries=5 -o Acquire::http::Timeout=20"
apt-get $APT update -q
apt-get $APT install -y -q --no-install-recommends \
  binutils libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-image0 \
  libxcb-render-util0 libxcb-xkb1 libxkbcommon-x11-0 libegl1 libgl1 libfontconfig1 \
  libdbus-1-3 libglib2.0-0 libx11-6 libx11-xcb1 libxext6 libxrender1 libxi6 libsm6 \
  libice6 libfreetype6 libxkbcommon0 xvfb xauth ca-certificates >/dev/null

pip install -q -r requirements.txt -r requirements-dev.txt
python packaging/build.py

# Informe: librerías que el núcleo de Qt y el plugin X11 no encuentran ni en el bundle ni en el sistema
INT="dist/KC Downloader/_internal"
for so in "$INT"/libQt6Core.so.6 "$INT"/libQt6Gui.so.6 "$INT"/libQt6Widgets.so.6 \
          "$INT"/PySide6/Qt/plugins/platforms/libqxcb.so; do
  [ -f "$so" ] || continue
  LD_LIBRARY_PATH="$INT:$INT/PySide6/Qt/lib" ldd "$so" | grep "not found" | sed "s|^|$(basename "$so"): |" || true
done

# Autotest del ejecutable bajo X11
export KCDL_HOME=/tmp/kcdl-selftest QT_QPA_PLATFORM=xcb
xvfb-run -a "dist/KC Downloader/kc-downloader" --selftest
cat "$KCDL_HOME/data/selftest.txt"
! grep -E "^(yt-dlp|ffmpeg|deno): falta|^https: fallo" "$KCDL_HOME/data/selftest.txt"

# Los archivos salen como root del contenedor: que el runner pueda tocarlos
chmod -R a+rwX dist build 2>/dev/null || true
