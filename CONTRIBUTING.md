# Contributing

Thanks for wanting to help! Bug reports, fixes and new ideas are all welcome.

## Set up

1. Install [uv](https://docs.astral.sh/uv/) and [ffmpeg](https://ffmpeg.org/download.html).
2. Fork this repository and clone your fork.
3. Run the app:

   ```
   uv run python app.py
   ```

   Then open http://127.0.0.1:8765.

## Before you open a pull request

```
uv run ruff check .
uv run pytest
```

Both must pass. GitHub Actions runs them, and also builds the Docker image, on every pull request.

## Guidelines

- Keep pull requests small and focused on one change.
- Add a test in `tests/` when you fix a bug or add behavior.
- If a site stops working, first try updating yt-dlp (`uv lock --upgrade-package yt-dlp`). Most breakages are fixed upstream within days.
- Don't add features that bypass DRM or paywalls.

## Reporting a bug

Open an issue with the link you tried (if it's public), what you expected, and the exact error message.
