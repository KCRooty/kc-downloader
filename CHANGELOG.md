# Changelog

All notable changes to KC Downloader are documented here.

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
