# TikTok Downloader Bot

## Overview

This is a Telegram bot that allows users to download TikTok videos. The bot includes both a chat interface and a web application interface.

Features:
- Download TikTok videos without watermarks
- Web interface for easy access
- Video caching to avoid repeated downloads
- Inline query support
- User download history
- SQLite database for storing video metadata

## Prerequisites

- Python 3.11+
- Telegram Bot Token (get from @BotFather)
- Docker (for containerized deployment)

## Local Development

1. Clone the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate it: `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and fill in your bot token
6. Run the bot: `python bot.py`

## Deploying to Render

For deployment instructions to Render, please see [DEPLOYMENT_RENDER.md](DEPLOYMENT_RENDER.md).

## Architecture

The application consists of:
- `bot.py`: Main Telegram bot application
- `database.py`: SQLite database management
- `downloader.py`: TikTok video downloading logic
- `webapp/`: Web interface files
- Dockerfile: Container configuration
- render.yaml: Render deployment configuration
