#!/usr/bin/env bash
set -o errexit

echo "Устанавливаем зависимости Python..."
pip install -U pip
pip install -r requirements.txt

echo "Устанавливаем FFmpeg..."
# Скачиваем официальный статический бинарник ffmpeg для Linux, если его еще нет
if [ ! -f "ffmpeg" ]; then
    wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
    tar -xf ffmpeg-release-amd64-static.tar.xz
    mv ffmpeg-*-amd64-static/ffmpeg ./
    mv ffmpeg-*-amd64-static/ffprobe ./
    rm -rf ffmpeg-*-amd64-static ffmpeg-release-amd64-static.tar.xz
    chmod +x ffmpeg ffprobe
fi
echo "FFmpeg успешно установлен!"