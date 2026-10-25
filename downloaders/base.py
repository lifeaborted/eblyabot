import asyncio
import os
import re
import socket
import subprocess
import time
import logging
import uuid
import yt_dlp
import requests
from abc import ABC, abstractmethod
from typing import Dict, Any, Callable, Optional

logger = logging.getLogger(__name__)
MAX_FILE_SIZE = 50 * 1024 * 1024


class BaseDownloader(ABC):
    def __init__(self, download_dir: str):
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)

    @property
    def proxy_url(self) -> Optional[str]:
        """Возвращает прокси из .env или локальный wireproxy (127.0.0.1:1080), если он запущен"""
        env_proxy = os.getenv('PROXY_URL')
        if env_proxy:
            return env_proxy
        try:
            with socket.create_connection(('127.0.0.1', 1080), timeout=0.3):
                return 'socks5://127.0.0.1:1080'
        except OSError:
            return None

    @property
    def proxies(self) -> Optional[Dict[str, str]]:
        """Словарь прокси для библиотеки requests"""
        p = self.proxy_url
        return {'http': p, 'https': p} if p else None

    @abstractmethod
    def get_ydl_opts(self) -> dict:
        pass

    def _fix_image(self, img_path: str) -> bool:
        """Конвертирует WebP/HEIC в чистый JPEG для Telegram"""
        tmp_path = img_path + ".tmp.jpg"
        cmd = [
            'ffmpeg', '-y',
            '-threads', '1',
            '-i', img_path,
            '-c:v', 'mjpeg',
            '-pix_fmt', 'yuv420p',
            '-map_metadata', '-1',
            '-frames:v', '1',
            tmp_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=30)
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 1024:
                os.replace(tmp_path, img_path)
                return True
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return False
        except Exception as e:
            logger.warning(f"Ошибка конвертации изображения {img_path}: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return False

    def _generate_thumbnail(self, video_path: str) -> Optional[str]:
        """Генерирует JPEG-превью <=320x320 из видеофайла по требованиям Telegram API"""
        thumb_path = f"{os.path.splitext(video_path)[0]}_thumb.jpg"
        cmd = [
            'ffmpeg', '-y',
            '-threads', '1',
            '-ss', '00:00:00.100',
            '-i', video_path,
            '-frames:v', '1',
            '-vf', 'scale=320:320:force_original_aspect_ratio=decrease',
            '-q:v', '5',
            thumb_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=30)
            if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                return thumb_path
        except Exception:
            pass
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        return None

    def _download_file(self, url: str, path: str, headers: dict, proxies: Optional[dict], timeout: int) -> bool:
        success = False
        try:
            with requests.get(url, headers=headers, proxies=proxies, timeout=timeout, stream=True) as response:
                content_length = response.headers.get('Content-Length', '')
                if response.status_code != 200 or (content_length.isdecimal() and int(content_length) > MAX_FILE_SIZE):
                    return False
                size = 0
                with open(path, 'wb') as output:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        size += len(chunk)
                        if size > MAX_FILE_SIZE:
                            return False
                        output.write(chunk)
                success = size > 1024
                return success
        finally:
            if not success and os.path.exists(path):
                os.remove(path)

    async def download(self, url: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        opts = self.get_ydl_opts()
        loop = asyncio.get_running_loop()
        run_id = uuid.uuid4().hex
        opts['outtmpl'] = opts['outtmpl'].replace('%(id)s', f'%(id)s_{run_id}')

        active_proxy = self.proxy_url
        if active_proxy:
            opts['proxy'] = active_proxy
        else:
            opts.pop('proxy', None)

        opts['logger'] = logging.getLogger('yt-dlp')
        opts['max_filesize'] = MAX_FILE_SIZE
        last_update_time = [0.0]

        def ytdl_hook(d):
            if d.get('status') == 'downloading' and d.get('downloaded_bytes', 0) > MAX_FILE_SIZE:
                raise ValueError('Файл превышает лимит 50 МБ')
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
        result = await asyncio.to_thread(self._sync_download, url, opts, run_id)
        if not result.get('success'):
            for entry in os.scandir(self.download_dir):
                if run_id in entry.name and entry.is_file():
                    os.remove(entry.path)
        return result

    def _sync_download(self, url: str, opts: dict, run_id: str) -> Dict[str, Any]:
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
                video_paths = []
                audio_path = None
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36'}

                # 1. Проверяем физические скачанные файлы в requested_downloads
                if 'requested_downloads' in info:
                    for req in info['requested_downloads']:
                        fp = req.get('filepath')
                        if fp and os.path.exists(fp):
                            ext = os.path.splitext(fp)[1].lower()
                            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                image_paths.append(fp)
                            elif ext in ['.mp3', '.m4a', '.wav', '.aac', '.ogg']:
                                audio_path = fp
                            elif ext in ['.mp4', '.mkv', '.webm', '.mov']:
                                video_paths.append(fp)

                # 2. Проверяем вложенные элементы (карусели Instagram / TikTok)
                if 'entries' in info and info['entries']:
                    for idx, entry in enumerate(info['entries']):
                        if not entry:
                            continue

                        entry_has_file = False
                        if 'requested_downloads' in entry:
                            for req in entry['requested_downloads']:
                                fp = req.get('filepath')
                                if fp and os.path.exists(fp):
                                    entry_has_file = True
                                    ext = os.path.splitext(fp)[1].lower()
                                    if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                        image_paths.append(fp)
                                    elif ext in ['.mp3', '.m4a', '.wav', '.aac', '.ogg']:
                                        audio_path = fp
                                    elif ext in ['.mp4', '.mkv', '.webm', '.mov']:
                                        video_paths.append(fp)

                        if not entry_has_file:
                            try:
                                fp = ydl.prepare_filename(entry)
                                mp4_fp = f"{os.path.splitext(fp)[0]}.mp4"
                                actual_fp = mp4_fp if os.path.exists(mp4_fp) else (fp if os.path.exists(fp) else None)
                                if actual_fp:
                                    entry_has_file = True
                                    ext = os.path.splitext(actual_fp)[1].lower()
                                    if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                        image_paths.append(actual_fp)
                                    elif ext in ['.mp3', '.m4a', '.wav', '.aac', '.ogg']:
                                        audio_path = fp
                                    elif ext in ['.mp4', '.mkv', '.webm', '.mov']:
                                        video_paths.append(actual_fp)
                            except Exception:
                                pass

                        # Если для слайда карусели нет видеофайла — качаем его картинку (Instagram / TikTok)
                        if not entry_has_file:
                            img_url = entry.get('url') or entry.get('thumbnail')
                            if not img_url and entry.get('thumbnails'):
                                img_url = entry['thumbnails'][-1].get('url')

                            if img_url:
                                out_path = os.path.join(self.download_dir, f"{info.get('id', 'post')}_{run_id}_img_{idx}.jpg")
                                try:
                                    if self._download_file(img_url, out_path, headers, self.proxies, 15) and self._fix_image(out_path):
                                        image_paths.append(out_path)
                                except Exception as e:
                                    logger.error(f"Не удалось скачать картинку слайда {img_url}: {e}")
                                if out_path not in image_paths and os.path.exists(out_path):
                                    os.remove(out_path)

                # Убираем дубликаты, сохраняя порядок слайдов
                image_paths = list(dict.fromkeys(image_paths))

                if image_paths:
                    for path in video_paths:
                        if os.path.exists(path):
                            os.remove(path)
                    return {
                        'success': True,
                        'media_type': 'images',
                        'image_paths': image_paths,
                        'audio_path': audio_path,
                        'title': title,
                        'description': description,
                        'uploader': uploader,
                        'tags': tags
                    }

                # 3. Если это обычное видео — ищем итоговый файл всеми способами
                single_filename = None
                if video_paths:
                    single_filename = video_paths[0]

                if not single_filename:
                    prepared = ydl.prepare_filename(info)
                    mp4_candidate = f"{os.path.splitext(prepared)[0]}.mp4"
                    if os.path.exists(mp4_candidate):
                        single_filename = mp4_candidate
                    elif os.path.exists(prepared):
                        single_filename = prepared

                if single_filename and os.path.exists(single_filename):
                    if os.path.getsize(single_filename) > MAX_FILE_SIZE:
                        return {'success': False, 'error': 'Файл превышает лимит 50 МБ'}
                    thumb_path = self._generate_thumbnail(single_filename)
                    return {
                        'success': True,
                        'media_type': 'video',
                        'file_path': single_filename,
                        'thumbnail_path': thumb_path,
                        'width': info.get('width'),
                        'height': info.get('height'),
                        'duration': int(info['duration']) if info.get('duration') else None,
                        'title': title,
                        'description': description,
                        'uploader': uploader,
                        'tags': tags
                    }

                # 4. Если это одиночный фото-пост (например, в Instagram, где нет видеоформатов)
                if not info.get('formats'):
                    img_url = info.get('thumbnail') or (info['thumbnails'][-1].get('url') if info.get('thumbnails') else None)
                    if img_url:
                        out_path = os.path.join(self.download_dir, f"{info.get('id', 'single')}_{run_id}_img.jpg")
                        try:
                            if self._download_file(img_url, out_path, headers, self.proxies, 15) and self._fix_image(out_path):
                                return {
                                    'success': True,
                                    'media_type': 'images',
                                    'image_paths': [out_path],
                                    'audio_path': None,
                                    'title': title,
                                    'description': description,
                                    'uploader': uploader,
                                    'tags': tags
                                }
                        except Exception as e:
                            logger.error(f"Не удалось скачать одиночное фото {img_url}: {e}")
                        if os.path.exists(out_path):
                            os.remove(out_path)

                return {'success': False, 'error': 'Файл не был найден на диске после скачивания.'}

        except Exception as e:
            logger.error(f"Ошибка при скачивании yt-dlp: {e}", exc_info=True)
            err = re.sub(r'\x1b\[[0-9;]*m', '', str(e)).replace('ERROR:', '').strip()
            return {'success': False, 'error': f'{err}'}
