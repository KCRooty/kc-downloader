import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kcdl import config, jobs, sources, tools  # noqa: E402


@pytest.fixture(autouse=True)
def portable_home(tmp_path, monkeypatch):
    monkeypatch.setenv("KCDL_HOME", str(tmp_path / "home"))
    return tmp_path


# ─── fuentes ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,src", [
    ("https://www.youtube.com/watch?v=abc", "youtube"),
    ("https://youtu.be/abc", "youtube"),
    ("https://m.youtube.com/watch?v=abc", "youtube"),
    ("https://music.youtube.com/watch?v=abc", "ytmusic"),
    ("https://open.spotify.com/track/xyz", "spotify"),
    ("spotify:track:xyz", "spotify"),
    ("https://www.pinterest.com/pin/123/", "pinterest"),
    ("https://es.pinterest.com/pin/123/", "pinterest"),
    ("https://pin.it/abc", "pinterest"),
    ("https://notyoutube.com.evil.net/x", None),
    ("https://example.com/youtube.com", None),
])
def test_detect_source(url, src):
    assert sources.detect_source(url) == src


def test_extract_urls_multiline():
    text = "mira esto https://youtu.be/a, y esto:\nhttps://open.spotify.com/track/b\nhttps://youtu.be/a"
    assert sources.extract_urls(text) == ["https://youtu.be/a", "https://open.spotify.com/track/b"]


# ─── ajustes ────────────────────────────────────────────────────────────────

def test_settings_roundtrip():
    s = config.Settings(accent="#123456", concurrent=4, proxy="socks5://x:1", tool_paths={"ffmpeg": "/x"})
    config.save(s)
    s2 = config.load()
    assert (s2.accent, s2.concurrent, s2.proxy, s2.tool_paths) == ("#123456", 4, "socks5://x:1", {"ffmpeg": "/x"})


def test_settings_bad_json_and_values():
    f = config.settings_file()
    f.parent.mkdir(parents=True)
    f.write_text("{no es json", encoding="utf-8")
    assert config.load().theme == "system"
    f.write_text(json.dumps({"theme": "neon", "concurrent": 99, "audio_kbps": "abc",
                             "video_res": "8K", "desconocido": 1}), encoding="utf-8")
    s = config.load()
    assert s.theme == "system" and s.concurrent == 6 and s.audio_kbps == 320 and s.video_res == "1080p"


# ─── órdenes ────────────────────────────────────────────────────────────────

def _tm(tmp_path):
    d = tmp_path / "tools"
    d.mkdir()
    for name in ("yt-dlp", "ffmpeg", "ffprobe", "deno", "spotdl"):
        (d / tools.exe_name(name)).write_bytes(b"")
    return tools.ToolManager(managed_dir=d, bundled_dir=tmp_path / "none")


def test_ytdlp_audio_cmd(tmp_path):
    s = config.Settings(dir_audio=str(tmp_path / "A"), cookies_browser="firefox", proxy="http://p:1")
    job = jobs.Job.from_settings("https://youtu.be/x", "youtube", "audio", s)
    cmd = jobs.ytdlp_cmd(job, s, _tm(tmp_path), tmp_path / "files.txt")
    assert cmd[0].endswith(tools.exe_name("yt-dlp"))
    i = cmd.index("--audio-format")
    assert cmd[i + 1] == "mp3" and "--audio-quality" in cmd and "--embed-thumbnail" in cmd
    assert cmd[cmd.index("--ffmpeg-location") + 1] == str(tmp_path / "tools")
    assert cmd[cmd.index("--cookies-from-browser") + 1] == "firefox"
    assert cmd[cmd.index("--proxy") + 1] == "http://p:1"
    assert cmd[cmd.index("-o") + 1].startswith(str(tmp_path / "A"))


def test_ytdlp_lossless_and_wav(tmp_path):
    s = config.Settings(audio_format="WAV")
    job = jobs.Job.from_settings("https://youtu.be/x", "youtube", "audio", s)
    cmd = jobs.ytdlp_cmd(job, s, _tm(tmp_path), tmp_path / "f")
    assert "--audio-quality" not in cmd and "--embed-thumbnail" not in cmd


def test_ytdlp_video_cmd(tmp_path):
    s = config.Settings(video_res="720p", video_fps="60", video_format="MKV", subtitles=True)
    job = jobs.Job.from_settings("https://youtu.be/x", "youtube", "video", s)
    cmd = jobs.ytdlp_cmd(job, s, _tm(tmp_path), tmp_path / "f")
    assert cmd[cmd.index("--merge-output-format") + 1] == "mkv"
    assert cmd[cmd.index("-S") + 1] == "res:720,fps:60"
    assert "--embed-subs" in cmd


def test_spotify_forced_to_audio_and_spotdl_cmd(tmp_path):
    s = config.Settings(audio_format="FLAC")
    job = jobs.Job.from_settings("https://open.spotify.com/album/x", "spotify", "video", s)
    assert job.mode == "audio"
    cmd = jobs.spotdl_cmd(job, s, _tm(tmp_path))
    assert cmd[cmd.index("--format") + 1] == "flac"
    assert cmd[cmd.index("--bitrate") + 1] == "disable"
    assert cmd[cmd.index("--ffmpeg") + 1].endswith(tools.exe_name("ffmpeg"))


# ─── progreso ───────────────────────────────────────────────────────────────

def test_parse_progress():
    assert jobs.parse_line("[KCPROG]  42.5%|  1.20MiB/s|00:12") == {"percent": 42.5, "speed": "1.20MiB/s", "eta": "00:12"}
    assert jobs.parse_line("[KCPROG]100.0%|NA|NA") == {"percent": 100.0, "speed": "", "eta": ""}
    assert jobs.parse_line("[download] Downloading item 3 of 12") == {"item": "3/12"}
    assert jobs.parse_line(r"[download] Destination: C:\x\Me at the zoo.f251.webm") == {"title": "Me at the zoo"}
    assert jobs.parse_line('[Merger] Merging formats into "/m/Cancion.mp4"') == {"title": "Cancion"}
    assert jobs.parse_line('Downloaded "Artista - Tema": https://music.youtube.com/x') == {"title": "Artista - Tema"}
    assert jobs.parse_line("[youtube] abc: Downloading webpage") == {}


# ─── herramientas ───────────────────────────────────────────────────────────

def test_tool_resolution_order(tmp_path):
    managed, bundled = tmp_path / "m", tmp_path / "b"
    managed.mkdir()
    bundled.mkdir()
    (bundled / tools.exe_name("ffmpeg")).write_bytes(b"")
    tm = tools.ToolManager(managed_dir=managed, bundled_dir=bundled)
    assert tm.find("ffmpeg").origin == "release"
    (managed / tools.exe_name("ffmpeg")).write_bytes(b"")
    assert tm.find("ffmpeg").origin == "app"
    manual = tmp_path / "manual-ffmpeg"
    manual.write_bytes(b"")
    tm.overrides["ffmpeg"] = str(manual)
    assert tm.find("ffmpeg").origin == "manual"
    dirs = tm.env()["PATH"].split(os.pathsep)
    assert str(tmp_path) in dirs[:len(tools.TOOLS)]


def test_sha256_formats():
    import hashlib
    data = b"hola"
    h = hashlib.sha256(data).hexdigest()
    tools._check_sha256(data, f"{h}  yt-dlp_linux\n{'0' * 64}  yt-dlp_linux_aarch64\n", "yt-dlp_linux")
    ps = f"Algorithm Hash Path\n--------- ---- ----\nSHA256 {h.upper()} D:\\a\\deno\\target\\deno.zip\n"
    tools._check_sha256(data, ps, "deno.zip")
    tools._check_sha256(data, h + "\n", "loquesea.zip")
    with pytest.raises(RuntimeError):
        tools._check_sha256(b"otro", f"{h}  x.zip\n", "x.zip")
    with pytest.raises(RuntimeError):
        tools._check_sha256(data, f"{h}  otro.zip\n{'1' * 64}  mas.zip\n", "x.zip")


def test_extract_members_zip_and_tar(tmp_path):
    import io
    import tarfile
    import zipfile
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr(f"ffmpeg-x/bin/{tools.exe_name('ffmpeg')}", b"F")
        z.writestr(f"ffmpeg-x/bin/{tools.exe_name('ffprobe')}", b"P")
        z.writestr("ffmpeg-x/doc/readme.txt", b"no")
    tools._extract_members(zbuf.getvalue(), "a.zip", ["ffmpeg", "ffprobe"], tmp_path / "z")
    assert sorted(p.name for p in (tmp_path / "z").iterdir()) == sorted(
        [tools.exe_name("ffmpeg"), tools.exe_name("ffprobe")])
    tbuf = io.BytesIO()
    with tarfile.open(fileobj=tbuf, mode="w:xz") as t:
        info = tarfile.TarInfo(f"x/bin/{tools.exe_name('deno')}")
        info.size = 1
        t.addfile(info, io.BytesIO(b"D"))
    tools._extract_members(tbuf.getvalue(), "a.tar.xz", ["deno"], tmp_path / "t")
    assert (tmp_path / "t" / tools.exe_name("deno")).read_bytes() == b"D"
    with pytest.raises(RuntimeError):
        tools._extract_members(tbuf.getvalue(), "a.tar.xz", ["ffmpeg"], tmp_path / "t2")


# ─── Spotify (embed) ────────────────────────────────────────────────────────

from kcdl import spotify  # noqa: E402


def _embed(entity: dict) -> str:
    data = {"props": {"pageProps": {"state": {"data": {"entity": entity}}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


def test_spotify_parse_url():
    assert spotify.parse_url("https://open.spotify.com/intl-es/track/4cOdK2wGLETKBW3PvgPWqT?si=x") == ("track", "4cOdK2wGLETKBW3PvgPWqT")
    assert spotify.parse_url("spotify:album:4aawyAB9vmqN3uQ7FjRGTy") == ("album", "4aawyAB9vmqN3uQ7FjRGTy")
    assert spotify.parse_url("https://open.spotify.com/artist/xyz1234567890") is None


def test_spotify_parse_embed_track_and_album():
    t = spotify.parse_embed(_embed({"type": "track", "name": "Tema", "artists": [{"name": "A"}, {"name": "B"}]}))
    assert (t.kind, t.tracks[0].query) == ("track", "A, B - Tema")
    a = spotify.parse_embed(_embed({"type": "album", "name": "Disco", "subtitle": "Grupo",
                                    "trackList": [{"title": "Uno", "subtitle": "Grupo, Invitado"},
                                                  {"title": "Dos", "subtitle": "Grupo"}]}))
    assert a.kind == "album" and [x.query for x in a.tracks] == ["Grupo, Invitado - Uno", "Grupo - Dos"]
    with pytest.raises(RuntimeError):
        spotify.parse_embed("<html>sin datos</html>")
    with pytest.raises(RuntimeError):
        spotify.parse_embed(_embed({"type": "playlist", "name": "Vacía", "trackList": []}))


def test_safe_folder():
    assert jobs.safe_folder('AC/DC: "Back" <in> Black?') == "AC_DC_ _Back_ _in_ Black_"
    assert jobs.safe_folder("...") == "Spotify"
