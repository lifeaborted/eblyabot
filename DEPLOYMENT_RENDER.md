# TikTok Downloader Bot - Render Deployment Guide

## Overview

This project is a Telegram bot that allows users to download TikTok videos. The bot includes both a chat interface and a web application interface. This guide provides instructions for deploying the application on Render using Docker.

## Project Structure

```
eblyabot/
├── bot.py                 # Main bot application
├── database.py           # SQLite database management
├── downloader.py         # TikTok video downloader
├── Dockerfile            # Render-optimized Docker configuration
├── render.yaml           # Render deployment configuration
├── requirements.txt      # Python dependencies
├── webapp/               # Web application frontend
│   ├── index.html
│   └── static/
├── .env.example          # Environment variables template
└── README.md             # This file
```

## Prerequisites

Before deploying to Render, you'll need:

1. **Telegram Bot Token**: Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. **Git repository**: Host your code on GitHub, GitLab, or Bitbucket
3. **Render account**: Sign up at [render.com](https://render.com)

## Deployment Steps

### 1. Prepare Your Repository

1. Push your updated code (including the new Dockerfile and render.yaml) to your Git repository
2. Ensure the following files are in your repository root inside the eblyabot directory:
   - `Dockerfile`
   - `render.yaml`
   - `requirements.txt`
   - `bot.py`
   - `database.py`
   - `downloader.py`
   - `webapp/` directory

### 2. Create a New Web Service on Render

1. Log in to your Render dashboard
2. Click "New +" and select "Web Service"
3. Connect your Git provider and select your repository
4. Select the branch you want to deploy (typically `main` or `master`)
5. Set the root directory to `eblyabot` (since your files are in the eblyabot subdirectory)
6. Render will automatically detect the Dockerfile and use the configuration from `render.yaml`

### 3. Configure Environment Variables

In your Render dashboard service settings, add the following environment variables:

| Key | Value | Required |
|-----|-------|----------|
| `BOT_TOKEN` | Your Telegram bot token from @BotFather | Yes |
| `TZ` | `Europe/Moscow` (or your preferred timezone) | Yes |

The `SERVER_URL` variable will be automatically populated by Render with your service's URL.

### 4. Environment Variables Details

- `BOT_TOKEN`: Get this by messaging [@BotFather](https://t.me/BotFather) on Telegram
- `SERVER_URL`: Automatically set by Render to your service URL (e.g., `https://your-service-name.onrender.com`)
- `PYTHONUNBUFFERED`: Set to `1` to ensure Python output is not buffered
- `DATABASE_DIR`: Directory for SQLite database (`/app/data`)
- `DOWNLOAD_DIR`: Directory for temporary video downloads (`/app/downloads`)
- `TZ`: Timezone for logging (`Europe/Moscow`)

## Important Notes for Render Deployment

### Database Configuration
- The application now supports both SQLite (default) and PostgreSQL
- For production deployments, it's recommended to use PostgreSQL
- When using PostgreSQL, set the `DB_TYPE` environment variable to `postgresql`
- Set the `DATABASE_URL` environment variable to your PostgreSQL connection string

### File Storage Limitations
- Render provides ephemeral storage which persists for about 15 minutes after the last write
- Don't rely on persistent file storage for downloaded videos
- With SQLite (default), the database will persist only as long as the container is running
- With PostgreSQL, data will persist across container restarts

### Port Configuration
- Render requires your application to listen on the port specified by the `PORT` environment variable
- The current bot.py may need to be updated to support the PORT environment variable

### Health Check
- The deployment includes a health check that pings the root URL
- Ensure your application is responsive on the root path

### Scaling Considerations
- Free tier on Render has 15-minute inactivity timeout
- Consider using the "Start a new instance" option in Render dashboard if you want to avoid cold starts

## Customization

### Changing Region
In the `render.yaml` file, you can change the region:
```yaml
region: frankfurt  # Options: frankfurt, oregon, virginia
```

### Resource Plan
In the `render.yaml` file, you can change the plan:
```yaml
plan: free  # or starter for more resources
```

### Dockerfile Customization
The provided Dockerfile is optimized for Render, but you can adjust:
- Python version
- System dependencies
- Working directory
- Port exposure

## Troubleshooting

### Bot Not Responding
- Check that your `BOT_TOKEN` is correctly set in Render dashboard
- Verify your bot privacy settings allow group messages if used in groups
- Check Render logs for error messages

### Download Issues
- Verify that ffmpeg is properly installed (it's included in the Dockerfile)
- Check logs for yt-dlp-related errors
- Ensure video size doesn't exceed Telegram's 50MB limit

### Web Interface Issues
- Confirm that the SERVER_URL is correctly set
- Verify that the web server is running on the correct port

### Database Problems
- Remember that SQLite database files are stored in ephemeral storage
- Data might be lost during container restarts
- Consider external database solutions for production use

## Updating Your Deployment

1. Make your changes to the code locally
2. Commit and push to your Git repository
3. Render will automatically deploy the new version
4. Monitor the build logs in your Render dashboard

## Security Considerations

- Never commit real bot tokens to your repository
- Use environment variables for all sensitive data
- The current implementation stores a SQLite database in ephemeral storage
- Consider implementing additional authentication for API endpoints in production

## Support

If you encounter issues with deployment:

1. Check the build logs in your Render dashboard
2. Review the runtime logs for application errors
3. Verify all environment variables are correctly set
4. Ensure your Dockerfile is properly configured

For more information on Render deployments, check the [Render documentation](https://render.com/docs).