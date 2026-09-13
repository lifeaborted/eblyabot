import asyncio
import os
import re
import time
import logging
import yt_dlp
from abc import ABC, abstractmethod
from typing import Dict, Any, Callable, Optional

logger = logging.getLogger(__name__)


class BaseDownloader(ABC):
    def __init__(self, download_dir: str):
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)

    @abstractmethod
    def get_ydl_opts(self) -> dict:
        pass

    async def download(self, url: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        opts = self.get_ydl_opts()
        loop = asyncio.get_running_loop()

        # Перенаправляем логи yt-dlp в нашу систему логирования
        opts['logger'] = logging.getLogger('yt-dlp')

        last_update_time = [0.0]

        def ytdl_hook(d):
            if d.get('status') == 'downloading' and progress_callback:
                current_time = time.time()
                if current_time - last_update_time[0] < 3.0:
                    return
                last_update_time[0] = current_time

                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes') or 0
                percent = (downloaded / total * 100) if total > 0 else 0
                speed = re.sub(r'\x1b\[[0-9;]*m', '', str(d.get('_speed_str', 'N/A'))).strip()
                eta = re.sub(r'\x1b\[[0-9;]*m', '', str(d.get('_eta_str', 'N/A'))).strip()
                asyncio.run_coroutine_threadsafe(progress_callback(percent, speed, eta), loop)

        opts['progress_hooks'] = [ytdl_hook]
        return await asyncio.to_thread(self._sync_download, url, opts)

    def _sync_download(self, url: str, opts: dict) -> Dict[str, Any]:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info: return {'success': False, 'error': 'Не удалось получить инфо'}
                return {
                    'success': True,
                    'media_type': 'video',
                    'file_path': ydl.prepare_filename(info),
                    'title': info.get('title', 'Media'),
                    'uploader': info.get('uploader', 'Unknown'),
                }
        except Exception as e:
            # <-- Теперь любая ошибка скачивания будет подробно писаться в лог
            logger.error(f"Ошибка при скачивании yt-dlp: {e}", exc_info=True)
            err = re.sub(r'\x1b\[[0-9;]*m', '', str(e)).replace('ERROR:', '').strip()
            return {'success': False, 'error': f'{err}'}