"""Leer canciones, álbumes y playlists de Spotify sin cuenta ni API.

La página pública de embed (open.spotify.com/embed/<tipo>/<id>) trae en
__NEXT_DATA__ el título y los artistas de cada pista. Con eso se busca
cada canción en YouTube Music y se baja con yt-dlp. Las playlists muy
largas pueden venir recortadas (el embed enseña las primeras ~100).
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from . import net

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

_URL = re.compile(r"(?:open\.spotify\.com/(?:intl-[a-z-]+/)?(?:embed/)?|spotify:)"
                  r"(track|album|playlist)[/:]([A-Za-z0-9]{10,})", re.IGNORECASE)
_NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', re.DOTALL)


@dataclass
class Track:
    artist: str
    title: str

    @property
    def query(self) -> str:
        return f"{self.artist} - {self.title}" if self.artist else self.title


@dataclass
class Entity:
    kind: str                     # track | album | playlist
    name: str
    owner: str = ""
    tracks: list = field(default_factory=list)


def parse_url(url: str) -> tuple[str, str] | None:
    m = _URL.search(url)
    return (m.group(1).lower(), m.group(2)) if m else None


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def parse_embed(html: str) -> Entity:
    m = _NEXT.search(html)
    if not m:
        raise RuntimeError("La página de Spotify no trae los datos esperados")
    data = json.loads(m.group(1))
    try:
        e = data["props"]["pageProps"]["state"]["data"]["entity"]
    except (KeyError, TypeError):
        raise RuntimeError("Spotify no devolvió información (enlace privado o inexistente)") from None
    kind = e.get("type", "")
    name = _clean(e.get("name") or e.get("title") or "")
    if kind == "track":
        artists = ", ".join(_clean(a.get("name", "")) for a in e.get("artists", []) if a.get("name"))
        return Entity("track", name, artists, [Track(artists, name)])
    tracks = [Track(_clean(t.get("subtitle", "")), _clean(t.get("title", "")))
              for t in e.get("trackList") or [] if t.get("title")]
    if not tracks:
        raise RuntimeError("La lista de Spotify está vacía o no es pública")
    return Entity(kind, name, _clean(e.get("subtitle", "")), tracks)


def fetch(url: str, timeout: float = 15) -> Entity:
    parsed = parse_url(url)
    if not parsed:
        raise RuntimeError("Enlace de Spotify no reconocido (canción, álbum o playlist)")
    kind, sid = parsed
    req = urllib.request.Request(f"https://open.spotify.com/embed/{kind}/{sid}",
                                 headers={"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9,en;q=0.8"})
    with net.urlopen(req, timeout=timeout) as r:
        html = r.read().decode("utf-8", errors="replace")
    return parse_embed(html)


def ytmusic_search_url(track: Track) -> str:
    """Búsqueda en YouTube Music limitada a canciones: el primer resultado
    suele ser el audio oficial ("Topic") con artista y álbum correctos."""
    return f"https://music.youtube.com/search?q={quote_plus(track.query)}#songs"
