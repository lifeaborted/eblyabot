# Use a standard Python 3.11 base image (not AWS Lambda specific)
FROM python:3.11-slim

# Install system dependencies including ffmpeg
RUN apt-get update && \
    apt-get install -y wget tar xz-utils curl ffmpeg && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create necessary directories
RUN mkdir -p downloads downloads_main data

# Expose port 8080 (Render's default)
EXPOSE 8080

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DATABASE_DIR=/app/data
ENV DOWNLOAD_DIR=/app/downloads

# Run the application
CMD ["python", "-u", "bot.py"]