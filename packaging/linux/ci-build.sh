#!/usr/bin/env bash
# Build de Linux dentro de python:3.12-slim-bullseye (Debian 11, glibc 2.31), para que
# el binario arranque también en Ubuntu 22.04/20.04 y Debian 11. PySide6 pide 2.28.
# Paquetes de deb.debian.org, no de los mirrors de Ubuntu de los runners.
# Uso (desde la raíz del repo): docker run --rm -v "$PWD:/src" -w /src python:3.12-slim-bullseye bash packaging/linux/ci-build.sh
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
APT="-o Acquire::Retries=5 -o Acquire::http::Timeout=20"
# Debian 11 ya no tiene soporte y su repo de seguridad lista paquetes que dan 404:
# solo el repo principal (las librerías van al bundle, no se ejecuta como servidor).
sed -i '/-security/d' /etc/apt/sources.list 2>/dev/null || true
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

# glibc más nueva que pide cualquier binario del paquete (app, Qt, yt-dlp, ffmpeg, deno...).
# Ubuntu 22.04 trae 2.35: si algo pide más, el build no vale para lo que promete.
MAXV=$(find "dist/KC Downloader" -type f -size +1k -exec sh -c 'head -c4 "$1" | grep -q ELF && objdump -T "$1" 2>/dev/null' _ {} \; \
  | grep -o 'GLIBC_[0-9.]*' | sort -u -V | tail -1)
echo "glibc mínima que necesita el paquete: ${MAXV:-ninguna}"
find "dist/KC Downloader" -type f -size +1k -print0 | while IFS= read -r -d '' f; do
  head -c4 "$f" | grep -q ELF || continue
  v=$(objdump -T "$f" 2>/dev/null | grep -o 'GLIBC_[0-9.]*' | sort -u -V | tail -1 || true)
  if [ "$v" = "$MAXV" ]; then echo "  la pide: ${f#dist/KC Downloader/}"; fi
done
[ "$(printf '%s\nGLIBC_2.35\n' "${MAXV:-GLIBC_2.0}" | sort -V | tail -1)" = "GLIBC_2.35" ] || { echo "ERROR: pide más que Ubuntu 22.04"; exit 1; }

# Autotest del ejecutable bajo X11
export KCDL_HOME=/tmp/kcdl-selftest QT_QPA_PLATFORM=xcb
xvfb-run -a "dist/KC Downloader/kc-downloader" --selftest
cat "$KCDL_HOME/data/selftest.txt"
! grep -E "^(yt-dlp|ffmpeg|deno): falta|^https: fallo" "$KCDL_HOME/data/selftest.txt"

# Los archivos salen como root del contenedor: que el runner pueda tocarlos
chmod -R a+rwX dist build 2>/dev/null || true
