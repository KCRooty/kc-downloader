#!/usr/bin/env bash
# KC Downloader — añade la app al menú de aplicaciones (solo para tu usuario, sin sudo).
# Ejecútalo desde la carpeta descomprimida:  ./install.sh      Para quitarla:  ./install.sh --remove
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/512x512/apps"
DESKTOP="$APPS/kc-downloader.desktop"

if [ "${1:-}" = "--remove" ]; then
    rm -f "$DESKTOP" "$ICONS/kc-downloader.png"
    echo "KC Downloader quitado del menú (la carpeta $DIR sigue donde estaba)."
    exit 0
fi

chmod +x "$DIR/kc-downloader" "$DIR"/tools/* "$DIR"/tools/realesrgan/realesrgan-ncnn-vulkan 2>/dev/null || true
mkdir -p "$APPS" "$ICONS"
cp "$DIR/_internal/assets/logo.png" "$ICONS/kc-downloader.png"
cat > "$DESKTOP" <<DESK
[Desktop Entry]
Type=Application
Name=KC Downloader
Comment=Descarga de YouTube, YouTube Music, Spotify y Pinterest
Exec="$DIR/kc-downloader"
Icon=kc-downloader
Terminal=false
Categories=AudioVideo;Network;
StartupWMClass=kc-downloader
DESK
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" >/dev/null 2>&1 || true
echo "Listo: KC Downloader está en el menú de aplicaciones."
