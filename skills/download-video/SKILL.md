---
name: download-video
description: Download a video or its audio from a link (YouTube, TikTok, Instagram, X/Twitter, Facebook, Vimeo, Reddit, Dailymotion, Twitch, SoundCloud and 1,800+ other sites, or any page with an HTML5 video) using AnyVideo Downloader. Use when the user pastes a video link and asks to download, save, grab or rip it, wants it as MP4, MP3 or M4A, wants a specific quality like 720p or 1080p, or asks which qualities a video has.
argument-hint: <video link> [quality, mp3/m4a, folder]
allowed-tools: Bash
---

# Download a video with AnyVideo Downloader

AnyVideo runs on the user's own computer through `uvx`, so nothing is uploaded anywhere.

## 1. Check the tools once

Run `uvx --version` and `ffmpeg -version`.

- If `uv` is missing, tell the user to install it from https://docs.astral.sh/uv/getting-started/installation/ and stop.
- If `ffmpeg` is missing, say that merging HD video and audio and converting to MP3 need it (https://ffmpeg.org/download.html). Direct single-file downloads still work without it.

Use this command prefix everywhere below:

```
uvx --from git+https://github.com/aethernode42/anyvideo-downloader anyvideo
```

The first run takes a minute while uv installs the dependencies. Later runs are fast.

## 2. Work out what the user wants

| The user asks for | Arguments |
|---|---|
| Just "download it" | `get "<link>"` (best quality, MP4 that plays everywhere) |
| A quality such as 720p | `get "<link>" -q 720` (best at or below that height) |
| Audio, MP3, music, podcast | `get "<link>" -a mp3` (or `-a m4a`) |
| A specific folder | add `-o "<folder>"`; otherwise it saves in the current folder |
| "What qualities are there?" | `info "<link>"` |
| An exact format from the `info` list | `get "<link>" -f <format id>` |

Always put the link in double quotes, because links often contain `&`.

## 3. Run it and report

Run the command with the Bash tool. Use a 10-minute timeout, since large videos take a while. When it finishes, it prints `Saved: <path>` for each file. Tell the user the full path.

For a playlist link, run `info` first, show the user the list, and ask which videos they want. Then download them one at a time.

## When it fails

Report the `Error:` line in plain words, and offer the matching fix:

- **"Could not reach this website"**: the address is wrong, or the user's network blocks that site. Don't try to get around a network block.
- **"No video was found on this page"**: the site isn't supported, or the video needs a login.
- **Needs a login** (Reddit, private Instagram, age-restricted YouTube): the user can export a `cookies.txt` from their browser and set `COOKIES_FILE=<path>`, or set `COOKIES_BROWSER=firefox`.
- **"DRM-protected"**: Netflix, Disney+ and some Vimeo videos can't be downloaded. Say so, and don't look for workarounds.
- **Live streams** can't be downloaded until they become a normal recording.
- **A site that used to work fails**: rerun the command with `uvx --refresh --from ...` to get the newest yt-dlp.

## Rules

- Only download what the user owns, what is in the public domain, or what they have permission to save. If the request is clearly piracy of paid content, decline.
- Never try to bypass DRM, paywalls or network blocks.
