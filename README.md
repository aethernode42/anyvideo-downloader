# AnyVideo Downloader

[![CI](https://github.com/aethernode42/anyvideo-downloader/actions/workflows/ci.yml/badge.svg)](https://github.com/aethernode42/anyvideo-downloader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Paste a link to a video, pick a quality, and download it as MP4, MP3 or M4A. It works with YouTube, TikTok, Instagram, Facebook, X, Vimeo, Dailymotion, Twitch, SoundCloud and [1,800+ other sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md), plus most pages that have a plain HTML5 video on them.

![AnyVideo Downloader screenshot](docs/screenshot.jpg)

## Features

- One-click **Best quality**, a button for each resolution, and **MP3 / M4A** audio extraction
- A full format table (video + audio, video only, audio only) with file sizes and codecs
- Separate video and audio streams merged into an MP4 that plays everywhere (H.264/AAC preferred)
- Live progress bar, with the file saved automatically when it's ready
- Playlists show a list of videos to pick from
- Shareable links: `/?url=<video link>` opens straight to that video
- Dark and light themes, works on phones
- Safe to host publicly: blocks links to private networks, rate-limits requests, and caps file size and simultaneous downloads

## Run it on your computer

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) and [ffmpeg](https://ffmpeg.org/download.html). For YouTube you also need [Deno](https://deno.com/) or [Node.js](https://nodejs.org/) 20+.

```
git clone https://github.com/aethernode42/anyvideo-downloader.git
cd anyvideo-downloader
uv run python app.py
```

Open http://127.0.0.1:8765. On Windows you can also double-click `run.bat` (it opens the browser for you), and on macOS/Linux you can run `./run.sh`.

The first run downloads the Python dependencies automatically.

## Run it with Docker

The image includes ffmpeg and Deno, so nothing else is needed:

```
docker build -t anyvideo .
docker run -p 8000:8000 anyvideo
```

Open http://127.0.0.1:8000.

## Deploy it

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/aethernode42/anyvideo-downloader)

The button uses [`render.yaml`](render.yaml) to create a free Docker web service. Any host that runs a Dockerfile works too (Railway, Fly.io, a VPS). Serverless hosts such as Vercel are a poor fit, because downloads run for a long time and produce large files.

**Note about YouTube on hosted servers:** YouTube often blocks requests from cloud data centers with "Sign in to confirm you're not a bot". Most other sites work fine from a server. For reliable YouTube downloads, run the app on your own computer.

## Settings

All settings are optional environment variables:

| Variable | Default | What it does |
|---|---|---|
| `PORT` | `8765` | Port to listen on. When set, the app listens on all interfaces. |
| `HOST` | `127.0.0.1` | Interface to listen on. |
| `MAX_CONCURRENT_JOBS` | `3` | Downloads that can run at the same time. |
| `MAX_FILESIZE_MB` | `2048` | Largest file allowed per download. `0` means no limit. |
| `RATE_LIMIT_PER_MIN` | `30` | API requests allowed per visitor per minute. `0` turns it off. |
| `JOB_TTL_SECONDS` | `3600` | How long finished files are kept before they're deleted. |
| `DOWNLOAD_DIR` | `.downloads` | Where files are stored while waiting to be saved. |
| `COOKIES_BROWSER` | unset | Use your browser's cookies (for example `firefox`) for sites that need a login. |
| `ALLOW_PRIVATE_URLS` | unset | Set to `1` to allow links to local network addresses (only for private use). |

### Sites that need a login

Reddit, private Instagram posts and age-restricted YouTube videos need cookies from a logged-in browser. Either export a Netscape-format `cookies.txt` (a "Get cookies.txt" browser extension can do this) and put it next to `app.py`, or set `COOKIES_BROWSER=firefox`. Only do this on your own computer, never on a public server.

## How it works

The backend is a small [FastAPI](https://fastapi.tiangolo.com/) app ([`app.py`](app.py)) built on [yt-dlp](https://github.com/yt-dlp/yt-dlp). The frontend is a single HTML file ([`static/index.html`](static/index.html)) with no build step.

| Endpoint | Purpose |
|---|---|
| `POST /api/info` `{url}` | Title, thumbnail, duration and every available format |
| `POST /api/jobs` `{url, mode, height?, format_id?}` | Starts a download. `mode` is `best`, `height`, `format`, `mp3` or `m4a`. |
| `GET /api/jobs/{id}` | Progress of a download |
| `GET /api/jobs/{id}/file` | The finished file |
| `GET /healthz` | Health check, including the yt-dlp version |

## Troubleshooting

- **"Could not reach this website"**: your network or internet provider may block that site, or the address is wrong.
- **A site that used to work stopped working**: sites change often. Update yt-dlp with `uv lock --upgrade-package yt-dlp && uv sync`.
- **"DRM-protected"**: streaming services such as Netflix and Disney+, and some Vimeo videos, use DRM. They can't be downloaded, by design.
- **YouTube fails on a hosted server**: see the note under [Deploy it](#deploy-it).

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) to get set up, and run `uv run pytest` before opening a pull request.

## Responsible use

Only download videos you own, that are in the public domain, or that you have permission to save. Respect the terms of service of the sites you use and the rights of creators.

## License

[MIT](LICENSE)
