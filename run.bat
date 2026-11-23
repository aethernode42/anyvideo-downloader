@echo off
rem Start AnyVideo Downloader from a cloned copy of this repo. Needs uv and ffmpeg.
cd /d "%~dp0"
uv run anyvideo serve
