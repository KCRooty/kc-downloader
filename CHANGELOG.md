# Changelog

All notable changes to KC Downloader are documented here.

## [Unreleased]

### Added
- **License: GPL-3.0.** The project now ships a `LICENSE` file; release packages
  include it from the next version on.

## [v3.0.1] - 2026-11-11

Linux release that also runs on older distros. No changes to the app itself.

### Fixed
- **Linux: Ubuntu 22.04 and other older distros.** The Linux build now runs inside
  Debian 11 instead of Debian 12, so the package needs glibc 2.30 instead of 2.36.
  Tested on a clean Ubuntu 22.04 and a clean Arch Linux. By glibc it should also run
  on Ubuntu 20.04, Linux Mint 20+, Debian 11+ and Fedora 32+, but those are not tested.
- **Linux:** `libxcb-randr` is now shipped inside the package, so the window opens on
  minimal installs that lack it.

### CI
- Every build reports the newest glibc any file in the package needs, and fails if it
  is newer than Ubuntu 22.04's (2.35).
- The Linux package is self-tested on a clean Ubuntu 22.04 (no certificates installed)
  and on a clean Arch Linux.

### Known issues
- Same as v3.0.0 below. The Linux build uses Debian 11, which no longer gets security
  updates; that only affects the system libraries copied into the package
  (X11/xcb helpers), not the downloads.

## [v3.0.0] - 2026-11-11

Full rewrite. Downloads work again on Windows and Linux, verified end to end with
only the tools shipped in the release (no Python, no system yt-dlp/ffmpeg).

### Changed
- **New interface (PySide6 / Qt)** replacing the Tkinter Winamp skin: light, dark or
  system theme, custom accent colour, adjustable font size. Queue with per-item
  progress, speed, ETA, open folder / retry / cancel / remove. Collapsible log.
  Drag & drop and Ctrl+V to add one or many links.
- **Settings window** (saved per user: `%APPDATA%\KC Downloader` / `~/.config/kc-downloader`):
  - Appearance: theme, accent, font size, show log.
  - Folders & names: one folder per mode (audio / video / image) and yt-dlp name
    templates for audio, video, Spotify and playlist folders.
  - Formats: audio MP3 / M4A / OPUS / OGG / FLAC / WAV with bitrate; video up to
    max resolution, 30/60 fps, MP4 / MKV / WEBM / MOV; embed cover and metadata;
    subtitles; auto-start on add.
  - Network & accounts: cookies from browser or `cookies.txt`, proxy, speed limit,
    parallel downloads (1–6).
  - Images: optional upscaling (Real-ESRGAN or Lanczos, x2/x3/x4).
- **Tool manager**: yt-dlp, FFmpeg and Deno (required), spotDL and Real-ESRGAN
  (optional). Lookup order: manual path → copy managed by the app → copy shipped
  in the release → system PATH. Install/update from the official releases with
  SHA-256 verification, into the user folder (no admin rights). Optional daily
  yt-dlp auto-update.
- **Spotify** no longer depends on spotDL: track / album / playlist are read from
  Spotify's public embed page and each song is fetched from YouTube Music.
  spotDL is kept only as a fallback.
- Releases are a folder (PyInstaller onedir) with `tools/` next to the executable.
  Linux bundle includes the X11 xcb libraries Qt needs, plus `install.sh` to add a
  menu entry.
- `--selftest` flag (writes a tool report and exits), used by CI.

### Fixed
- Downloads failing on every machine (v2.3–v2.4). Root causes:
  - Windows: the bundled `ffmpeg`/`ffprobe` were Chocolatey shims pointing at the
    build machine, so they did nothing elsewhere.
  - YouTube now requires a JavaScript runtime; Deno was missing.
  - Linux: spotDL missing data files (pykakasi) and yt-dlp packaged as a Python
    zipapp that needed a system Python.
  - spotDL 4.6.0 can no longer get a Spotify token (upstream breakage).
- Exit crash under X11 on Linux.
- Found by testing the Linux release on a clean Arch Linux (same base as CachyOS),
  not on the machine that built it:
  - every HTTPS request made by the app itself (Spotify, Pinterest, installing
    tools) failed with `CERTIFICATE_VERIFY_FAILED`: the bundled Python looked for
    certificates where Debian keeps them. The app now ships its own (certifi) and
    also uses the system store.
  - the window did not open under X11: the xcb libraries Qt needs were silently
    left out of the build. The build now stops if any is missing.
- The bundled tools no longer inherit PyInstaller's internal environment
  (`_PYI_*`, `LD_LIBRARY_PATH`), which can confuse yt-dlp / spotDL (also
  PyInstaller programs) and the file manager on Linux.
- On Wayland the app falls back to X11 (XWayland) if the Wayland plugin fails.

### Known issues
- Spotify playlists are limited to what the embed page lists (about 100 tracks).
- Spotify songs are matched by "artist - title" search: on rare tracks the first
  YouTube Music result may be a different version.
- The spotDL fallback is broken upstream; it only helps if a future spotDL fixes it.
- Not verified yet: Pinterest **video**, a real Real-ESRGAN upscale run, a real
  CachyOS/KDE desktop on Wayland, and the GitHub Actions workflow itself. Tested
  so far: the built executables downloading YouTube audio/video and Spotify
  (track and album) on Windows 11 with an empty PATH, Debian 13 and a clean Arch
  Linux (window under X11/Xvfb + downloads), all in WSL2.
- Real-ESRGAN publishes no checksums, so its download is the only one not verified
  by SHA-256.
- Linux needs glibc 2.36+ (Ubuntu 24.04+, Mint 22+, Debian 12+, Fedora 37+, Arch, CachyOS…; not Ubuntu 22.04) and a desktop with OpenGL/EGL (`libEGL`), which any normal desktop distro has.
- The release archive is big (~260 MB Windows, ~290 MB Linux) because it carries
  FFmpeg, Deno and Real-ESRGAN.
- YouTube may ask some IPs to "confirm you're not a bot"; use cookies from your
  browser in Settings → Network & accounts.

## [v2.4] - 2026-10-09

### Added
- Bundle hardening: cookies template, `ffprobe`, and `spotdl` are now guaranteed to be packaged with the release (previously could be missing depending on the build environment).
- CI release workflow switched to the `gh` CLI for GitHub API calls (was failing silently on `Invoke-RestMethod` without auth on some runners).

### Known issues
- **The app opens and starts, but downloads currently fail with an error.** This affects both the Windows and Linux builds.
- **Not verified working on any machine other than the one it was built on.** The goal is a true plug-and-play bundle (no Python/pip needed) — the dependencies are packaged, but the bundle has not been confirmed to actually run a download end-to-end on a clean machine.
- Real-ESRGAN upscaling is Windows-only; the Linux release does not include `realesrgan-ncnn-vulkan`.

## [v2.3] - 2026-10-08

### Added
- Initial public release: YouTube / YouTube Music / Spotify / Pinterest downloads via `yt-dlp` + `spotdl`.
- Real-ESRGAN image upscaling (Windows only): `ultrasharp-4x` and `upscayl-lite-4x` models.
- Winamp Classic Dark UI.
- Queue system for multiple URLs.

### Known issues
- Same download failure and cross-machine issues as v2.4 (present since this first release, not something v2.4 introduced).
