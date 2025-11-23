# Render Dashboard Configuration Guide

## Service Creation Steps

1. **Login to Render Dashboard**
   - Go to https://dashboard.render.com
   - Sign in with your account

2. **Create New Web Service**
   - Click "New +" in the top navigation
   - Select "Web Service"
   - Connect to your Git provider (GitHub, GitLab, or Bitbucket)

3. **Select Repository**
   - Find and select your repository containing the TikTok bot
   - Click "Continue"

4. **Configure Environment**
   - **Name**: Give your service a name (e.g., `tiktok-downloader-bot`)
   - **Environment**: Docker
   - **Root Directory**: Enter `eblyabot` (since your files are in the eblyabot subdirectory)
   - **Branch**: Select your main branch (usually `main` or `master`)
   - **Region**: Select your preferred region (Frankfurt, Oregon, or Virginia)
   - **Plan**: Choose Free tier (sufficient for basic usage)

5. **Set Environment Variables**
   - Click on "Advanced" to reveal environment variables section
   - Add the following variables:

   | Key | Value | Description |
   |-----|-------|-------------|
   | `BOT_TOKEN` | Your actual bot token from @BotFather | Required - never commit this to code |
   | `TZ` | `Europe/Moscow` | Timezone for logs |

   > **Note**: Do NOT add SERVER_URL here - Render will set this automatically

6. **Review and Create**
   - Verify all settings match your requirements
   - Click "Create Web Service"

## Post-Deployment Configuration

### 1. Verify Environment Variables
- After deployment, go to your service dashboard
- Click on "Environment" tab
- Confirm that BOT_TOKEN is set correctly
- Check that all required variables appear (excluding SERVER_URL which is auto-generated)

### 2. Check Service Health
- Go to the "Manual Deploy" section
- Check the build logs to ensure there were no errors
- Monitor the service logs after startup

### 3. Update Bot Webhook (if using webhooks)
- If you plan to use webhooks instead of polling, you'll need to update the bot to register the webhook URL
- Current implementation uses polling, which works fine with this setup

### 4. Get Your Service URL
- After successful deployment, your service URL will be visible in the dashboard
- It will be in the format: `https://your-service-name.onrender.com`
- This URL will be automatically available as `SERVER_URL` to your application
- Update any external references to use this URL

## Common Issues and Solutions

### 1. Build Failures
- Check build logs in the "Manual Deploy" section
- Ensure all dependencies in requirements.txt are valid
- Verify Dockerfile syntax

### 2. Runtime Errors
- Check service logs in the "Logs" section
- Verify that BOT_TOKEN is correctly set
- Confirm the application is binding to the correct port

### 3. Bot Not Responding
- Check that your bot privacy settings allow it to receive messages
- Verify the bot token is correct
- Check service logs for connection errors

### 4. Web Interface Not Loading
- Verify that your SERVER_URL environment variable is being used correctly
- Ensure the web server starts on the correct port
- Check that static files are being served properly

## Environment Variables Reference

| Variable | Required | Value | Notes |
|----------|----------|-------|-------|
| `BOT_TOKEN` | Yes | Your Telegram bot token | Get from @BotFather |
| `TZ` | Yes | `Europe/Moscow` | Timezone setting |
| `DB_TYPE` | No | `sqlite` or `postgresql` | Database type (defaults to sqlite) |
| `DATABASE_URL` | Conditional | PostgreSQL connection string | Required only when DB_TYPE=postgresql |
| `PYTHONUNBUFFERED` | No | `1` | Auto-configured in Dockerfile |
| `DATABASE_DIR` | No | `/app/data` | Auto-configured in Dockerfile |
| `DOWNLOAD_DIR` | No | `/app/downloads` | Auto-configured in Dockerfile |
| `SERVER_URL` | No | Auto-generated | Set automatically by Render |

## Scaling Options

### Free Tier Limitations
- 15 minutes of inactivity before instance hibernation
- 750 hours per month of runtime
- Basic CPU and memory resources

## Scaling Options

### Free Tier Limitations
- 15 minutes of inactivity before instance hibernation
- 750 hours per month of runtime
- Basic CPU and memory resources

### Upgrading Considerations
- If you need more uptime, consider upgrading to "Starter" plan
- For higher traffic, consider "Standard" or "Pro" plans
- More resources help with video processing tasks

## Database Configuration

### Using SQLite (Default)
- Set `DB_TYPE` to `sqlite` (or leave unset, as it's the default)
- No `DATABASE_URL` needed
- Data will be stored in ephemeral storage and may be lost between deployments

### Using PostgreSQL (Recommended for Production)
1. Create a PostgreSQL instance on Render:
   - Go to your Render dashboard
   - Click "New +" and select "PostgreSQL"
   - Configure your database settings
   - Note the connection string provided

2. Configure your web service:
   - Set `DB_TYPE` to `postgresql`
   - Set `DATABASE_URL` to the connection string from your PostgreSQL instance
   - The connection will be persistent across deployments

### Migrating from SQLite to PostgreSQL
If you already have data in SQLite and want to migrate to PostgreSQL:
1. Deploy with PostgreSQL configuration
2. Your application will create new tables in PostgreSQL
3. The old SQLite data will not be automatically migrated

## Security Best Practices

1. Keep your BOT_TOKEN secret
2. Regularly rotate your bot token
3. Monitor access logs if possible
4. Be aware that Render's ephemeral storage is not persistent
5. Consider backup solutions for important data

## Maintenance Tasks

1. Regularly check logs for errors
2. Monitor service availability
3. Update dependencies in requirements.txt periodically
4. Watch for new versions of the Docker base image