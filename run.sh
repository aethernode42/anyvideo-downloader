#!/usr/bin/env sh
# Start AnyVideo Downloader from a cloned copy of this repo. Needs uv and ffmpeg.
cd "$(dirname "$0")" && exec uv run anyvideo serve
