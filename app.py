"""AnyVideo Downloader: paste a link, get every downloadable format.

Backend: FastAPI + yt-dlp (1,800+ supported sites, plus a generic extractor
that finds <video>, og:video and HLS/DASH manifests on any page).
"""

from __future__ import annotations

import ipaddress
import os
import re
import secrets
import shutil
import socket
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yt_dlp
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).parent


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# ---------- settings (all optional, via environment variables) ----------
DL_DIR = Path(os.environ.get("DOWNLOAD_DIR", ROOT / ".downloads"))
JOB_TTL = _env_int("JOB_TTL_SECONDS", 3600)              # delete finished files after this
MAX_CONCURRENT_JOBS = _env_int("MAX_CONCURRENT_JOBS", 3)  # downloads running at once
MAX_FILESIZE_MB = _env_int("MAX_FILESIZE_MB", 2048)       # per download, 0 = unlimited
RATE_LIMIT_PER_MIN = _env_int("RATE_LIMIT_PER_MIN", 30)   # API calls per IP per minute, 0 = off
ALLOW_PRIVATE_URLS = os.environ.get("ALLOW_PRIVATE_URLS") == "1"

DL_DIR.mkdir(parents=True, exist_ok=True)

BASE_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "socket_timeout": 20,
    "retries": 3,
    # YouTube needs a JavaScript runtime for signature solving (Deno or Node).
    "js_runtimes": {"deno": {}, "node": {}},
}
if MAX_FILESIZE_MB > 0:
    BASE_OPTS["max_filesize"] = MAX_FILESIZE_MB * 1024 * 1024

# Login-gated sites (Reddit, private Instagram, age-restricted YouTube...):
# drop a Netscape cookies.txt next to app.py, or set COOKIES_BROWSER=firefox.
if (ROOT / "cookies.txt").exists():
    BASE_OPTS["cookiefile"] = str(ROOT / "cookies.txt")
elif os.environ.get("COOKIES_BROWSER"):
    BASE_OPTS["cookiesfrombrowser"] = (os.environ["COOKIES_BROWSER"],)

app = FastAPI(title="AnyVideo Downloader")


# ---------- helpers ----------

def _clean_err(e: Exception) -> str:
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")
    if "DRM protected" in msg:
        return "This video is DRM-protected by the site, so it can't be downloaded."
    if "File is larger than max-filesize" in msg or "max_filesize" in msg:
        return f"This file is larger than the {MAX_FILESIZE_MB} MB limit of this server."
    if "getaddrinfo failed" in msg or "Name or service not known" in msg or "Failed to resolve" in msg:
        return "Could not reach this website. Your network or internet provider may be blocking it."
    if msg.startswith("Unsupported URL"):
        return "No video was found on this page. The site may not be supported, or the video may need a login."
    return msg


def normalize_url(raw: str) -> str:
    """Add a scheme if missing and refuse URLs that point at private networks.

    Blocking private/loopback/link-local addresses stops a public deployment
    from being used to reach internal services (SSRF).
    """
    url = raw.strip()
    if not url:
        raise HTTPException(400, "Please paste a link.")
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.IGNORECASE):
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise HTTPException(400, "Only http:// and https:// links are supported.")
    if not ALLOW_PRIVATE_URLS:
        try:
            infos = socket.getaddrinfo(parts.hostname, None)
        except socket.gaierror:
            raise HTTPException(400, f"Could not reach '{parts.hostname}'. The address may be wrong, "
                                     "or your network/internet provider may be blocking this site.")
        for info in infos:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
            if not ip.is_global:
                raise HTTPException(400, "Links to local or private network addresses are not allowed.")
    return url


_HITS: dict[str, deque] = defaultdict(deque)
_HITS_LOCK = threading.Lock()


def rate_limit(request: Request) -> None:
    if RATE_LIMIT_PER_MIN <= 0:
        return
    ip = request.client.host if request.client else "?"  # uvicorn applies proxy headers
    now = time.time()
    with _HITS_LOCK:
        q = _HITS[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_LIMIT_PER_MIN:
            raise HTTPException(429, "Too many requests. Please wait a minute and try again.")
        q.append(now)


def _fallback_url(url: str, err: str) -> str | None:
    """Alternate URL to retry when a site's main page blocks anonymous access."""
    m = re.match(r"https?://(?:www\.)?vimeo\.com/(?:.*/)?(\d+)", url)
    if m and "logged-in" in err:
        return f"https://player.vimeo.com/video/{m.group(1)}"
    return None


# ---------- info ----------

class InfoRequest(BaseModel):
    url: str


def _fmt(f: dict) -> dict:
    vcodec, acodec = f.get("vcodec") or "none", f.get("acodec") or "none"
    has_v, has_a = vcodec != "none", acodec != "none"
    # Unknown codecs (common on generic/direct links) = assume muxed.
    if f.get("vcodec") is None and f.get("acodec") is None:
        has_v = has_a = True
    kind = "av" if has_v and has_a else ("video" if has_v else "audio")
    return {
        "id": f.get("format_id"),
        "ext": f.get("ext"),
        "kind": kind,
        "height": f.get("height"),
        "fps": f.get("fps"),
        "abr": f.get("abr"),
        "tbr": f.get("tbr"),
        "vcodec": vcodec,
        "acodec": acodec,
        "size": f.get("filesize") or f.get("filesize_approx"),
        "note": f.get("format_note") or f.get("format") or "",
        "protocol": f.get("protocol"),
    }


def summarize(info: dict) -> dict:
    raw = info.get("formats") or [info]
    formats = [_fmt(f) for f in raw if f.get("url") or f.get("format_id")]
    # Drop storyboards / images.
    formats = [f for f in formats if f["ext"] not in ("mhtml", "jpg", "png", "webp")]
    heights = sorted({f["height"] for f in formats if f["kind"] != "audio" and f["height"]}, reverse=True)
    return {
        "type": "video",
        "id": info.get("id"),
        "title": info.get("title") or "video",
        "uploader": info.get("uploader") or info.get("channel"),
        "site": info.get("extractor_key") or info.get("extractor"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "webpage_url": info.get("webpage_url") or info.get("original_url"),
        "heights": heights,
        "has_audio": any(f["kind"] in ("av", "audio") for f in formats),
        "formats": formats,
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "yt_dlp": yt_dlp.version.__version__}


@app.post("/api/info")
def get_info(req: InfoRequest, request: Request) -> dict:
    rate_limit(request)
    url = normalize_url(req.url)
    opts = {**BASE_OPTS, "extract_flat": "in_playlist"}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        msg = _clean_err(e)
        alt = _fallback_url(url, msg)
        if not alt:
            raise HTTPException(422, msg)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(alt, download=False)
            url = alt
        except yt_dlp.utils.DownloadError:
            raise HTTPException(422, msg)
    if info.get("_type") == "playlist":
        entries = [
            {"title": e.get("title") or e.get("url"), "url": e.get("url") or e.get("webpage_url"),
             "duration": e.get("duration"), "thumbnail": (e.get("thumbnails") or [{}])[-1].get("url")}
            for e in (info.get("entries") or []) if e
        ]
        return {"type": "playlist", "title": info.get("title"), "site": info.get("extractor_key"),
                "entries": entries[:200]}
    return {**summarize(info), "resolved_url": url}


# ---------- download jobs ----------

class JobRequest(BaseModel):
    url: str
    mode: str = "best"          # best | height | format | mp3 | m4a
    height: int | None = None
    format_id: str | None = None


JOBS: dict[str, dict] = {}
LOCK = threading.Lock()


def format_selector(req: JobRequest) -> tuple[str, dict]:
    extra: dict[str, Any] = {}
    if req.mode in ("mp3", "m4a"):
        extra["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": req.mode,
                                    "preferredquality": "320" if req.mode == "mp3" else "0"}]
        return "bestaudio/best", extra
    if req.mode == "height" and req.height:
        h = int(req.height)
        # Prefer H.264/AAC so the MP4 plays everywhere, fall back to anything.
        return (f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/bv*[height<={h}]+ba/"
                f"b[height<={h}]/bv*+ba/b"), {"merge_output_format": "mp4"}
    if req.mode == "format" and req.format_id:
        if not re.fullmatch(r"[\w.\-]+", req.format_id):
            raise HTTPException(400, "Invalid format id.")
        fid = req.format_id
        return f"{fid}+ba/{fid}", {"merge_output_format": "mp4"}
    return "bv*[vcodec^=avc1]+ba[ext=m4a]/b[vcodec~='^(avc|h264)']/bv*+ba/b", {"merge_output_format": "mp4"}


def _run_job(job_id: str, url: str, fmt: str, extra: dict) -> None:
    job = JOBS[job_id]
    out_dir = DL_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    def hook(d: dict) -> None:
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            job.update(status="downloading", downloaded=done, total=total,
                       speed=d.get("speed"), eta=d.get("eta"),
                       progress=(done / total * 100) if total else None)
        elif d["status"] == "finished":
            job.update(status="processing", progress=100)

    def pp_hook(d: dict) -> None:
        if d["status"] == "started":
            job.update(status="processing")

    opts = {**BASE_OPTS, **extra, "format": fmt,
            "outtmpl": str(out_dir / "%(title).150B [%(id)s].%(ext)s"),
            "windowsfilenames": True,
            "progress_hooks": [hook], "postprocessor_hooks": [pp_hook],
            "concurrent_fragment_downloads": 4}
    try:
        for attempt in range(2):  # YouTube sometimes 403s a fresh URL; one retry fixes it
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.extract_info(url, download=True)
                break
            except yt_dlp.utils.DownloadError as e:
                if attempt or "403" not in str(e):
                    raise
                job.update(status="queued", progress=0)
        files = [p for p in out_dir.iterdir() if p.is_file() and not p.name.endswith((".part", ".ytdl"))]
        if not files:
            # yt-dlp skips (without raising) files over max_filesize.
            raise RuntimeError(f"No file was produced. It may be larger than the {MAX_FILESIZE_MB} MB limit.")
        f = max(files, key=lambda p: p.stat().st_size)
        job.update(status="done", file=str(f), filename=f.name, size=f.stat().st_size, progress=100)
    except Exception as e:  # noqa: BLE001
        job.update(status="error", error=_clean_err(e))
        shutil.rmtree(out_dir, ignore_errors=True)
    finally:
        job["finished_at"] = time.time()


def cleanup() -> None:
    now = time.time()
    with LOCK:
        for jid, job in list(JOBS.items()):
            if job.get("finished_at") and now - job["finished_at"] > JOB_TTL:
                shutil.rmtree(DL_DIR / jid, ignore_errors=True)
                JOBS.pop(jid, None)
        # Orphans from previous runs (the job list lives in memory only).
        for d in DL_DIR.iterdir():
            if d.is_dir() and d.name not in JOBS and now - d.stat().st_mtime > JOB_TTL:
                shutil.rmtree(d, ignore_errors=True)


@app.post("/api/jobs")
def create_job(req: JobRequest, request: Request) -> dict:
    rate_limit(request)
    cleanup()
    url = normalize_url(req.url)
    fmt, extra = format_selector(req)
    with LOCK:
        running = sum(1 for j in JOBS.values() if not j.get("finished_at"))
        if running >= MAX_CONCURRENT_JOBS:
            raise HTTPException(429, "The server is busy with other downloads. Please try again shortly.")
        job_id = secrets.token_hex(16)  # unguessable, so nobody can fetch someone else's file
        JOBS[job_id] = {"id": job_id, "status": "queued", "progress": 0, "created": time.time()}
    threading.Thread(target=_run_job, args=(job_id, url, fmt, extra), daemon=True).start()
    return {"id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {k: v for k, v in job.items() if k != "file"}


@app.get("/api/jobs/{job_id}/file")
def job_file(job_id: str) -> FileResponse:
    job = JOBS.get(job_id)
    if not job or job.get("status") != "done" or not Path(job["file"]).exists():
        raise HTTPException(404, "File not ready or already deleted")
    return FileResponse(job["file"], filename=job["filename"], media_type="application/octet-stream")


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    # Hosting platforms (Render, Railway, Fly...) set PORT; then listen on all interfaces.
    port = _env_int("PORT", 8765)
    host = os.environ.get("HOST", "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    uvicorn.run(app, host=host, port=port, proxy_headers=True, forwarded_allow_ips="*")
