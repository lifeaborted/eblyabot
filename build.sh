#!/usr/bin/env bash
set -o errexit

CONFIG_PATH="warp.conf"
if [ -f "/etc/secrets/warp.conf" ]; then
    CONFIG_PATH="/etc/secrets/warp.conf"
fi

echo "Запуск Cloudflare WARP SOCKS5 (Конфиг: $CONFIG_PATH)..."

# Запускаем прокси, но теперь все его ошибки перехватываем в файл warp.log
wireproxy -c "$CONFIG_PATH" > warp.log 2>&1 &

# Даем прокси 4 секунды на попытку подключения
sleep 4

# Выводим логи прокси в консоль Render, чтобы мы их увидели
echo "=== ЛОГИ WIREPROXY ==="
cat warp.log
echo "======================"

echo "Запуск Telegram бота..."
exec python -u bot.py