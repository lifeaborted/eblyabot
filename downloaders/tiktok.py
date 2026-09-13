import asyncio
import os
import requests
import logging
from typing import Optional, Callable
from .base import BaseDownloader

logger = logging.getLogger(__name__)


class TiktokDownloader(BaseDownloader):
    def get_ydl_opts(self) -> dict:
        return {
            # Для слайдшоу yt-dlp скачивает несколько файлов, autonumber предотвратит перезапись
            'outtmpl': f'{self.download_dir}/%(id)s_%(autonumber)s.%(ext)s',
            'quiet': False,
            'merge_output_format': 'mp4',
            'extractor_args': {'tiktok': {'language': 'en', 'country': 'US'}},
        }

    def _resolve_url(self, url: str) -> str:
        if 'vm.tiktok.com' in url.lower() or 'vt.tiktok.com' in url.lower():
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
                return response.url
            except Exception as e:
                logger.warning(f"Не удалось развернуть короткую ссылку {url}: {e}")
        return url

    async def download(self, url: str, progress_callback: Optional[Callable] = None):
        # Разворачиваем укороченные ссылки
        full_url = await asyncio.to_thread(self._resolve_url, url)
        clean_url = full_url.split('?')[0]

        # Полностью доверяем скачивание yt-dlp
        return await super().download(clean_url, progress_callback)