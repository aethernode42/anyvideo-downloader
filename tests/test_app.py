"""Offline tests (no internet needed). Run with: uv run pytest"""

import os

os.environ["RATE_LIMIT_PER_MIN"] = "1000"

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app as appmod

client = TestClient(appmod.app)


def test_homepage_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "AnyVideo" in r.text


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8765/",
    "http://localhost/admin",
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
    "http://10.0.0.5/video.mp4",
    "http://192.168.1.1/",
    "http://[::1]/",
])
def test_private_urls_blocked(url):
    with pytest.raises(HTTPException) as e:
        appmod.normalize_url(url)
    assert e.value.status_code == 400


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/a.mp4", "   "])
def test_bad_schemes_rejected(url):
    with pytest.raises(HTTPException):
        appmod.normalize_url(url)


def test_scheme_added(monkeypatch):
    monkeypatch.setattr(appmod.socket, "getaddrinfo",
                        lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 0))])
    assert appmod.normalize_url("example.com/v/1") == "https://example.com/v/1"


def test_info_rejects_private_url_via_api():
    r = client.post("/api/info", json={"url": "http://127.0.0.1/"})
    assert r.status_code == 400


def test_job_rejects_bad_format_id(monkeypatch):
    monkeypatch.setattr(appmod, "normalize_url", lambda u: u)
    r = client.post("/api/jobs", json={"url": "https://example.com", "mode": "format", "format_id": "x; rm -rf"})
    assert r.status_code == 400


def test_unknown_job_404():
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/api/jobs/nope/file").status_code == 404


def test_format_selectors():
    sel, extra = appmod.format_selector(appmod.JobRequest(url="x", mode="mp3"))
    assert sel == "bestaudio/best" and extra["postprocessors"][0]["preferredcodec"] == "mp3"
    sel, extra = appmod.format_selector(appmod.JobRequest(url="x", mode="height", height=720))
    assert "height<=720" in sel and extra["merge_output_format"] == "mp4"
    sel, _ = appmod.format_selector(appmod.JobRequest(url="x", mode="format", format_id="137"))
    assert sel == "137+ba/137"
    sel, _ = appmod.format_selector(appmod.JobRequest(url="x"))
    assert sel.startswith("bv*")


def test_summarize_groups_formats():
    info = {
        "id": "abc", "title": "Test", "extractor_key": "Fake", "duration": 10,
        "formats": [
            {"format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "height": 360, "url": "u"},
            {"format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "height": 1080, "url": "u"},
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a", "url": "u"},
            {"format_id": "sb0", "ext": "mhtml", "vcodec": "none", "acodec": "none", "url": "u"},
        ],
    }
    s = appmod.summarize(info)
    kinds = {f["id"]: f["kind"] for f in s["formats"]}
    assert kinds == {"18": "av", "137": "video", "140": "audio"}  # storyboard dropped
    assert s["heights"] == [1080, 360]
    assert s["has_audio"] is True


def test_direct_file_unknown_codecs_counts_as_av():
    s = appmod.summarize({"id": "f", "title": "f", "url": "https://x/f.mp4", "ext": "mp4", "format_id": "0"})
    assert s["formats"][0]["kind"] == "av"


def test_friendly_errors():
    assert "DRM" in appmod._clean_err(Exception("ERROR: This format is DRM protected"))
    assert "blocking" in appmod._clean_err(Exception("[Errno 11001] getaddrinfo failed"))
    assert "No video" in appmod._clean_err(Exception("ERROR: Unsupported URL: https://example.com/"))


def test_vimeo_fallback():
    assert appmod._fallback_url("https://vimeo.com/76979871", "only works when logged-in") == \
        "https://player.vimeo.com/video/76979871"
    assert appmod._fallback_url("https://youtube.com/x", "logged-in") is None


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(appmod, "RATE_LIMIT_PER_MIN", 2)
    appmod._HITS.clear()
    codes = [client.post("/api/info", json={"url": "http://127.0.0.1/"}).status_code for _ in range(3)]
    assert codes == [400, 400, 429]
    appmod._HITS.clear()


def test_busy_server_returns_429(monkeypatch):
    monkeypatch.setattr(appmod, "normalize_url", lambda u: u)
    monkeypatch.setattr(appmod, "MAX_CONCURRENT_JOBS", 0)
    r = client.post("/api/jobs", json={"url": "https://example.com"})
    assert r.status_code == 429
