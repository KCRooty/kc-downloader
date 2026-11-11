"""Descargas reales (red + herramientas). Solo con KCDL_E2E=1.

Usa las herramientas que encuentre el ToolManager (gestionadas, de la
release o del sistema). KCDL_E2E_STRICT=1 exige que NINGUNA venga del
sistema: así se comprueba un PC limpio.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kcdl import config, jobs, tools  # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get("KCDL_E2E") != "1", reason="KCDL_E2E=1 para descargas reales")

VIDEO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"      # "Me at the zoo", 19 s
TRACK = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"


@pytest.fixture
def env(tmp_path, monkeypatch):
    s = config.Settings(dir_audio=str(tmp_path / "A"), dir_video=str(tmp_path / "V"),
                        dir_image=str(tmp_path / "I"))
    bundle = os.environ.get("KCDL_E2E_BUNDLE")   # carpeta tools/ de una release ya montada
    if bundle:
        # PC limpio: fuera del PATH todo lo que no sea del propio sistema operativo
        keep = [p for p in os.environ["PATH"].split(os.pathsep)
                if p.lower().startswith(("c:\\windows", "/usr/bin", "/bin"))]
        monkeypatch.setenv("PATH", os.pathsep.join(keep))
        monkeypatch.setenv("KCDL_HOME", str(tmp_path / "home"))
    tm = tools.ToolManager(bundled_dir=Path(bundle)) if bundle else tools.ToolManager()
    if os.environ.get("KCDL_E2E_STRICT") == "1":
        for k in ("yt-dlp", "ffmpeg", "deno"):
            f = tm.find(k)
            assert f and f.origin != "sistema", f"{k} viene del sistema o falta: {f}"
    return s, tm


def _run(job, s, tm):
    log = []
    ok = jobs.Runner(job, s, tm, lambda kind, data: log.append((kind, data))).run()
    text = "\n".join(str(d) for k, d in log if k == "log")
    assert ok, f"falló: {job.error}\n{text[-3000:]}"
    assert "JavaScript runtime" not in text, "yt-dlp no encontró deno"
    return job


def test_youtube_audio_mp3(env):
    s, tm = env
    job = _run(jobs.Job.from_settings(VIDEO, "youtube", "audio", s), *env)
    assert job.files and job.files[0].endswith(".mp3") and Path(job.files[0]).stat().st_size > 50_000
    assert job.title == "Me at the zoo"


def test_youtube_video_mp4(env):
    s, tm = env
    job = _run(jobs.Job.from_settings(VIDEO, "youtube", "video", s), *env)
    assert job.files and job.files[0].endswith(".mp4")


def test_spotify_track(env):
    s, tm = env
    job = _run(jobs.Job.from_settings(TRACK, "spotify", "audio", s), *env)
    assert job.files and any(f.endswith(".mp3") for f in job.files)
