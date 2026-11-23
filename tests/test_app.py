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


# ---------- review fixes ----------

def _proxy_request(raw: bytes) -> bytes:
    import socket
    from urllib.parse import urlsplit

    u = urlsplit(appmod.BASE_OPTS["proxy"])
    with socket.create_connection((u.hostname, u.port), timeout=10) as s:
        s.sendall(raw)
        return s.recv(4096)


@pytest.mark.parametrize("target", ["127.0.0.1:80", "localhost:8765", "169.254.169.254:80", "10.0.0.1:443", "[::1]:80"])
def test_proxy_refuses_private_https_tunnels(target):
    reply = _proxy_request(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
    assert reply.startswith(b"HTTP/1.1 403")


@pytest.mark.parametrize("url", ["http://127.0.0.1:8765/healthz", "http://192.168.1.1/", "http://169.254.169.254/latest/"])
def test_proxy_refuses_private_plain_http(url):
    reply = _proxy_request(f"GET {url} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
    assert reply.startswith(b"HTTP/1.1 403")


def test_proxy_refuses_mixed_dns_answers(monkeypatch):
    # A hostname that returns one public and one private address is refused (DNS rebinding trick).
    monkeypatch.setattr(appmod, "_real_getaddrinfo", lambda *a, **k: [
        (2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(PermissionError):
        appmod.open_public_connection("rebind.example", 443)


def test_all_ytdlp_traffic_uses_the_proxy():
    assert appmod.BASE_OPTS["proxy"].startswith("http://127.0.0.1:")


def test_blocked_error_is_friendly():
    assert "private" in appmod._clean_err(Exception("HTTP Error 403: Blocked Private Address"))
    assert "private" in appmod._clean_err(Exception("CONNECT tunnel failed, response 403"))


@pytest.mark.parametrize("fid", ["all", "mergeall", "best", "BV", "ba", "x" * 81])
def test_multi_format_keywords_rejected(fid):
    with pytest.raises(HTTPException):
        appmod.format_selector(appmod.JobRequest(url="x", mode="format", format_id=fid))


def test_unsafe_protocols_refused():
    import yt_dlp

    appmod.check_protocols({"protocol": "https"})
    appmod.check_protocols({"requested_formats": [{"protocol": "m3u8_native"}, {"protocol": "https"}]})
    for proto in ("rtmp", "rtsp", "f4m", "ism", None):
        with pytest.raises(yt_dlp.utils.DownloadError):
            appmod.check_protocols({"requested_formats": [{"protocol": "https"}, {"protocol": proto}]})


def test_forwarded_for_header_is_not_trusted(monkeypatch):
    monkeypatch.setattr(appmod, "RATE_LIMIT_PER_MIN", 2)
    appmod._HITS.clear()
    codes = [client.post("/api/info", json={"url": "http://127.0.0.1/"},
                         headers={"X-Forwarded-For": f"1.2.3.{i}"}).status_code for i in range(3)]
    assert codes[-1] == 429
    appmod._HITS.clear()


def test_configured_client_ip_header(monkeypatch):
    monkeypatch.setattr(appmod, "CLIENT_IP_HEADER", "cf-connecting-ip")
    req = type("R", (), {"headers": {"cf-connecting-ip": "8.8.8.8"}, "client": None})()
    assert appmod.client_ip(req) == "8.8.8.8"


def test_rate_table_is_pruned(monkeypatch):
    appmod._HITS.clear()
    for i in range(10_001):
        appmod._HITS[f"ip{i}"]  # stale empty entries
    req = type("R", (), {"headers": {}, "client": type("C", (), {"host": "9.9.9.9"})()})()
    appmod.rate_limit(req)
    assert len(appmod._HITS) == 1
    appmod._HITS.clear()


def test_job_status_is_a_copy():
    appmod.JOBS["t1"] = {"id": "t1", "status": "done", "file": "/secret/path", "progress": 100}
    try:
        r = client.get("/api/jobs/t1").json()
        assert r["status"] == "done" and "file" not in r
    finally:
        appmod.JOBS.pop("t1")


def test_live_streams_and_ffmpeg_network_disabled():
    assert appmod.BASE_OPTS["external_downloader"] == {"default": "native"}
    assert appmod.BASE_OPTS["playlistend"] == 200


def test_proxy_never_reuses_plain_http_connection_for_another_host(monkeypatch):
    import socket
    import threading
    from urllib.parse import urlsplit

    # A keep-alive server that ignores "Connection: close" and answers every request with "A".
    srv = socket.create_server(("127.0.0.1", 0))
    seen = []

    def serve():
        conn, _ = srv.accept()
        with conn:
            buf = b""
            while True:
                data = conn.recv(65536)
                if not data:
                    return
                buf += data
                while b"\r\n\r\n" in buf:
                    req, _, buf = buf.partition(b"\r\n\r\n")
                    seen.append(req.split(b"\r\n")[0])
                    conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\nConnection: keep-alive\r\n\r\nA")

    threading.Thread(target=serve, daemon=True).start()
    port = srv.getsockname()[1]
    monkeypatch.setattr(appmod, "open_public_connection",
                        lambda host, p: socket.create_connection(("127.0.0.1", port)))

    u = urlsplit(appmod.BASE_OPTS["proxy"])
    with socket.create_connection((u.hostname, u.port), timeout=5) as s:
        s.sendall(b"GET http://a.example/ HTTP/1.1\r\nHost: a.example\r\n\r\n")
        first = b""
        while not first.endswith(b"A"):
            first += s.recv(4096)
        assert b"Connection: close" in first and b"keep-alive" not in first.lower()
        # A client that reuses the connection anyway must not reach anything.
        s.sendall(b"GET http://b.example/secret HTTP/1.1\r\nHost: b.example\r\nCookie: x=1\r\n\r\n")
        try:
            rest = s.recv(4096)
        except OSError:
            rest = b""
        assert rest == b""
    srv.close()
    assert seen == [b"GET / HTTP/1.1"]
