#!/usr/bin/env bash
set -o errexit

# Ищем конфиг либо в секретах Render, либо в текущей папке
CONFIG_PATH="warp.conf"
if [ -f "/etc/secrets/warp.conf" ]; then
    CONFIG_PATH="/etc/secrets/warp.conf"
fi

echo "Запуск Cloudflare WARP SOCKS5 (Конфиг: $CONFIG_PATH)..."
wireproxy -c "$CONFIG_PATH" &

# Даем прокси время на подключение
sleep 3

echo "Запуск Telegram бота..."
exec python -u bot.py