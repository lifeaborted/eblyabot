#!/usr/bin/env bash
set -o errexit

echo "Запуск Cloudflare WARP SOCKS5..."
# Запускаем wireproxy в фоне
wireproxy -c warp.conf &

# Даем прокси 3 секунды на инициализацию
sleep 3

echo "Запуск Telegram бота..."
exec python -u bot.py