import asyncio
import os
import re
import time
import logging
import yt_dlp
import requests
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
                if not info:
                    return {'success': False, 'error': 'Не удалось получить метаданные по ссылке.'}

                title = info.get('title', '')
                description = info.get('description', '')
                uploader = info.get('uploader') or info.get('creator') or info.get('channel') or 'Unknown'
                tags = info.get('tags', [])

                image_paths = []
                audio_path = None

                # 1. yt-dlp собирает физические скачанные файлы в блоке requested_downloads
                if 'requested_downloads' in info:
                    for req in info['requested_downloads']:
                        fp = req.get('filepath')
                        if fp and os.path.exists(fp):
                            ext = os.path.splitext(fp)[1].lower()
                            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                image_paths.append(fp)
                            elif ext in ['.mp3', '.m4a', '.wav', '.aac', '.ogg']:
                                audio_path = fp

                # 2. Проверяем вложенные элементы (актуально для каруселей TikTok)
                if 'entries' in info and info['entries']:
                    for entry in info['entries']:
                        if not entry: continue

                        if 'requested_downloads' in entry:
                            for req in entry['requested_downloads']:
                                fp = req.get('filepath')
                                if fp and os.path.exists(fp):
                                    ext = os.path.splitext(fp)[1].lower()
                                    if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                        image_paths.append(fp)
                                    elif ext in ['.mp3', '.m4a', '.wav', '.aac', '.ogg']:
                                        audio_path = fp
                        else:
                            try:
                                fp = ydl.prepare_filename(entry)
                                if os.path.exists(fp):
                                    ext = os.path.splitext(fp)[1].lower()
                                    if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                        image_paths.append(fp)
                                    elif ext in ['.mp3', '.m4a', '.wav', '.aac', '.ogg']:
                                        audio_path = fp
                            except Exception:
                                pass

                    # ФОЛБЭК: Если yt-dlp достал только ссылки на картинки, но не сохранил их сам
                    if not image_paths:
                        for idx, entry in enumerate(info['entries']):
                            img_url = entry.get('url')
                            if img_url and (entry.get('ext', '').lower() in ['jpg', 'jpeg', 'png',
                                                                             'webp'] or '/obj/' in img_url):
                                out_path = os.path.join(self.download_dir, f"{info.get('id')}_img_{idx}.jpg")
                                try:
                                    r = requests.get(img_url, timeout=10)
                                    if r.status_code == 200:
                                        with open(out_path, 'wb') as f:
                                            f.write(r.content)
                                        image_paths.append(out_path)
                                except Exception as e:
                                    logger.error(f"Не удалось вручную скачать картинку {img_url}: {e}")

                # Убираем дубликаты
                image_paths = sorted(list(set(image_paths)))

                if image_paths:
                    return {
                        'success': True,
                        'media_type': 'images',
                        'image_paths': image_paths,
                        'audio_path': audio_path,
                        'title': title,
                        'uploader': uploader
                    }

                # 3. Если это обычное видео
                single_filename = ydl.prepare_filename(info)
                if not os.path.exists(single_filename):
                    if 'requested_downloads' in info and info['requested_downloads']:
                        single_filename = info['requested_downloads'][0].get('filepath')

                if single_filename and os.path.exists(single_filename):
                    return {
                        'success': True,
                        'media_type': 'video',
                        'file_path': single_filename,
                        'title': title,
                        'description': description,
                        'uploader': uploader,
                        'tags': tags
                    }
                else:
                    return {'success': False, 'error': 'Файл не был найден на диске после скачивания.'}

        except Exception as e:
            logger.error(f"Ошибка при скачивании yt-dlp: {e}", exc_info=True)
            err = re.sub(r'\x1b\[[0-9;]*m', '', str(e)).replace('ERROR:', '').strip()
            return {'success': False, 'error': f'{err}'}