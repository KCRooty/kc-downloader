"""Detección del origen de una URL."""

from __future__ import annotations

import re
from urllib.parse import urlparse

SOURCES = {
    "youtube": "YouTube",
    "ytmusic": "YouTube Music",
    "spotify": "Spotify",
    "pinterest": "Pinterest",
}

_URL_RE = re.compile(r"(https?://\S+|spotify:\S+)", re.IGNORECASE)


def detect_source(url: str) -> str | None:
    u = url.strip().lower()
    if u.startswith("spotify:"):
        return "spotify"
    host = urlparse(u if "://" in u else "https://" + u).hostname or ""
    if host.startswith("www."):
        host = host[4:]
    if host == "open.spotify.com":
        return "spotify"
    if host == "music.youtube.com":
        return "ytmusic"
    if host in ("youtube.com", "m.youtube.com", "youtu.be", "youtube-nocookie.com"):
        return "youtube"
    if host == "pin.it" or host.startswith("pinterest.") or ".pinterest." in host:
        return "pinterest"
    return None


def extract_urls(text: str) -> list[str]:
    """Saca todas las URLs de un texto pegado (una o varias, en cualquier formato)."""
    seen: list[str] = []
    for m in _URL_RE.finditer(text):
        url = m.group(1).rstrip(".,;)\"'>")
        if url not in seen:
            seen.append(url)
    return seen
