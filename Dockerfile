# Используем стандартный образ Python 3.11[cite: 4]
FROM python:3.11-slim

# Устанавливаем ffmpeg и Node.js (критично для капчи YouTube)
RUN apt-get update && \
    apt-get install -y wget tar xz-utils curl ffmpeg && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Устанавливаем рабочую директорию[cite: 4]
WORKDIR /app

# Копируем зависимости и устанавливаем их[cite: 4]
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код[cite: 4]
COPY . .

# Создаем директории и выдаем права[cite: 4]
RUN mkdir -p downloads downloads_main data
RUN chmod -R 755 /app/downloads /app/downloads_main /app/data

# Открываем порт 8080[cite: 4]
EXPOSE 8080

# Переменные окружения[cite: 4]
ENV PYTHONUNBUFFERED=1
ENV DATABASE_DIR=/app/data
ENV DOWNLOAD_DIR=/app/downloads

# Запуск[cite: 4]
CMD ["python", "-u", "bot.py"]