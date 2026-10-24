# Repository Guidelines

## Project Structure & Module Organization

This Python 3.11+ project runs an aiogram Telegram bot and an aiohttp server in one process. `bot.py` starts both. Put Telegram routes in `handlers/`, service selection and yt-dlp logic in `downloaders/`, HTTP routes in `web_server.py`, and browser assets in `webapp/`. `database.py` handles SQLite and PostgreSQL; `config.py` reads environment settings; `utils/` contains shared formatting, URL, logging, and cleanup helpers. Deployment files include `Dockerfile`, `render.yaml`, and the Render guides. There is currently no `tests/` directory.

## Build, Test, and Development Commands

- `python -m venv venv && source venv/bin/activate` creates and activates a local environment.
- `pip install -r requirements.txt` installs dependencies. The requirements file is UTF-16 LE encoded.
- `python -m compileall -q bot.py config.py database.py web_server.py handlers downloaders utils` checks Python syntax without starting the bot.
- `python bot.py` runs Telegram polling and the HTTP server; set `BOT_TOKEN` first. The server uses `PORT`, defaulting to `8080`.

## Coding Style & Naming Conventions

Use four-space indentation, `snake_case` for functions and modules, and `PascalCase` for classes. Follow the style of adjacent code; no formatter or linter configuration is present. Keep changes in the existing modules and avoid adding dependencies for small tasks. Preserve downloader result fields such as `success`, `media_type`, file paths, and metadata because Telegram and HTTP callers consume them.

## Testing Guidelines

No automated test framework or coverage threshold is configured. For behavior changes, add a focused `test_*.py` test that uses stubs or local files instead of Telegram or media-service requests. Run the syntax check above after Python edits. Check both Telegram and Web App paths when changing shared downloads or API payloads, including cached Telegram `file_id` reuse and temporary-file cleanup.

## Commit & Pull Request Guidelines

Recent commits use short subjects such as `fix: ffmpeg ram usage` and `feat: added instagram support`; use a concise `fix:`, `feat:`, or `ref:` prefix. In pull requests, describe the behavior changed, verification performed, and any linked issue. Include screenshots for `webapp/` UI changes.

## Security & Configuration

Keep secrets in environment variables. Do not print, edit, or commit `.env`, `cookies.txt`, `bot_data.db`, logs, or downloaded media. Validate incoming URLs, JSON, and file names; preserve HTML-safe bot messages and existing database records.
