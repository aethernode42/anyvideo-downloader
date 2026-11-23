#!/usr/bin/env sh
# Start AnyVideo Downloader on macOS / Linux. Needs uv and ffmpeg installed.
cd "$(dirname "$0")" && uv run python app.py
