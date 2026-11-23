"""Command line for AnyVideo Downloader.

    anyvideo                      open the web app in your browser
    anyvideo <link>               download the best quality into the current folder
    anyvideo get <link> [...]     download with options (quality, audio only, folder)
    anyvideo info <link>          list title and available formats
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from pathlib import Path


def _core():
    from anyvideo import app as core  # imported lazily so --help stays fast

    return core


def _fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def _resolve(core, url: str) -> str:
    from fastapi import HTTPException

    try:
        return core.normalize_url(url)
    except HTTPException as e:
        _fail(e.detail)


def cmd_serve(args: argparse.Namespace) -> None:
    import os

    core = _core()
    port = args.port or int(os.environ.get("PORT", "8765"))
    host = args.host or os.environ.get("HOST", "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}"
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [url]).start()
    print(f"AnyVideo Downloader is running at {url}  (press Ctrl+C to stop)")
    core.serve(host=host, port=port)


def cmd_get(args: argparse.Namespace) -> None:
    import yt_dlp

    core = _core()
    url = _resolve(core, args.url)
    if args.audio:
        mode = args.audio
    elif args.format:
        mode = "format"
    elif args.quality:
        mode = "height"
    else:
        mode = "best"
    from fastapi import HTTPException

    try:
        fmt, extra = core.format_selector(
            core.JobRequest(url=url, mode=mode, height=args.quality, format_id=args.format))
    except HTTPException as e:
        _fail(e.detail)
    out = Path(args.output).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    opts = {**core.BASE_OPTS, **extra, "format": fmt, "quiet": False, "noprogress": False,
            "outtmpl": str(out / "%(title).150B [%(id)s].%(ext)s"), "windowsfilenames": True,
            "concurrent_fragment_downloads": 4}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get("_type") == "playlist":
                _fail("This is a playlist. Run 'anyvideo info' on it, then download the videos one by one.")
            if info.get("is_live"):
                _fail("Live streams can't be downloaded.")
            core.check_protocols(info)
            result = ydl.process_ie_result(info, download=True)
    except yt_dlp.utils.YoutubeDLError as e:
        _fail(core._clean_err(e))
    for d in (result or {}).get("requested_downloads") or []:
        print(f"Saved: {d.get('filepath')}")


def cmd_info(args: argparse.Namespace) -> None:
    from fastapi import HTTPException

    core = _core()
    url = _resolve(core, args.url)
    try:
        data = core._get_info(url)
    except HTTPException as e:
        _fail(e.detail)
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    if data["type"] == "playlist":
        print(f"Playlist: {data.get('title')} ({len(data['entries'])} videos)")
        for e in data["entries"]:
            print(f"  {e['url']}  {e['title']}")
        return
    print(f"{data['title']}  [{data['site']}]")
    if data.get("heights"):
        print("Qualities: " + ", ".join(f"{h}p" for h in data["heights"]))
    print(f"{'ID':<28}{'KIND':<7}{'EXT':<6}{'QUALITY':<10}SIZE")
    for f in data["formats"]:
        quality = f"{f['height']}p" if f.get("height") else (f"{round(f['abr'])}k" if f.get("abr") else "")
        size = f"{f['size'] / 1e6:.1f} MB" if f.get("size") else ""
        print(f"{str(f['id'])[:27]:<28}{f['kind']:<7}{f['ext']!s:<6}{quality:<10}{size}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="anyvideo", description="Download videos from YouTube, TikTok, "
                                "Instagram, X and 1,800+ other sites.")
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("serve", help="open the web app (default)")
    s.add_argument("--host", help="interface to listen on (default 127.0.0.1, or 0.0.0.0 when PORT is set)")
    s.add_argument("--port", type=int, help="port (default 8765, or $PORT)")
    s.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    s.set_defaults(func=cmd_serve)

    g = sub.add_parser("get", help="download a video")
    g.add_argument("url")
    g.add_argument("-o", "--output", default=".", help="folder to save into (default: current folder)")
    g.add_argument("-q", "--quality", type=int, metavar="HEIGHT", help="max height, e.g. 720 or 1080")
    g.add_argument("-a", "--audio", choices=["mp3", "m4a"], help="save audio only")
    g.add_argument("-f", "--format", metavar="ID", help="exact format id from 'anyvideo info'")
    g.set_defaults(func=cmd_get)

    i = sub.add_parser("info", help="show title and available formats")
    i.add_argument("url")
    i.add_argument("--json", action="store_true", help="print machine-readable JSON")
    i.set_defaults(func=cmd_info)
    return p


def _safe_output() -> None:
    """Never crash on titles with emoji or other scripts (e.g. a Windows console set to cp1252).
    When output goes to another program (pipes, Claude), use UTF-8 so file paths stay exact."""
    for stream in (sys.stdout, sys.stderr):
        if not hasattr(stream, "reconfigure"):
            continue
        if stream.isatty():
            stream.reconfigure(errors="replace")
        else:
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> None:
    _safe_output()
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0].lower().startswith(("http://", "https://", "www.")):
        argv.insert(0, "get")  # "anyvideo <link>" is a shortcut for "anyvideo get <link>"
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        args = build_parser().parse_args(["serve", *argv])
    args.func(args)


if __name__ == "__main__":
    main()
