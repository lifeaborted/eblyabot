# Используем стандартный образ Python 3.11
FROM python:3.11-slim

# Устанавливаем ffmpeg, Node.js и curl для скачивания
RUN apt-get update && \
    apt-get install -y wget tar xz-utils curl ffmpeg && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# === НОВОЕ: Устанавливаем wireproxy для WARP ===
RUN wget -qO wireproxy.tar.gz https://github.com/pufferffish/wireproxy/releases/download/v1.0.7/wireproxy_linux_amd64.tar.gz && \
    tar -xzf wireproxy.tar.gz && \
    mv wireproxy /usr/local/bin/ && \
    rm wireproxy.tar.gz && \
    chmod +x /usr/local/bin/wireproxy

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код (включая warp.conf и start.sh)
COPY . .

# Создаем директории, выдаем права и делаем скрипт исполняемым
RUN mkdir -p downloads downloads_main data
RUN chmod -R 755 /app/downloads /app/downloads_main /app/data
RUN chmod +x build.sh

# Открываем порт 8080
EXPOSE 8080

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV DATABASE_DIR=/app/data
ENV DOWNLOAD_DIR=/app/downloads

# === НОВОЕ: Запуск через наш bash-скрипт ===
CMD ["./build.sh"]