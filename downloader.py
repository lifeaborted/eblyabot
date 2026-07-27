import re
import os
import time
import logging
import asyncio
import requests
import yt_dlp
from typing import Dict, Any, List, Callable, Optional
from config import DOWNLOAD_DIR

logger = logging.getLogger(__name__)


def make_progress_bar(percent: float, length: int = 10) -> str:
    """Генерация строки прогресс-бара"""
    percent = max(0.0, min(100.0, percent))
    filled = int(round(length * percent / 100))
    bar = '█' * filled + '░' * (length - filled)
    return f"[{bar}] {percent:.1f}%"


class MediaDownloader:
    def __init__(self):
        self.download_dir = DOWNLOAD_DIR
        os.makedirs(self.download_dir, exist_ok=True)

    def is_supported_url(self, url: str) -> bool:
        """Проверка, поддерживается ли URL (TikTok или YouTube)"""
        url_lower = url.lower()
        tiktok_domains = ['tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com']
        youtube_domains = ['youtube.com', 'youtu.be', 'm.youtube.com']

        return any(domain in url_lower for domain in tiktok_domains + youtube_domains)

    def get_service_type(self, url: str) -> str:
        """Определение сервиса по URL"""
        url_lower = url.lower()
        if any(d in url_lower for d in ['tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com']):
            return 'tiktok'
        if any(d in url_lower for d in ['youtube.com', 'youtu.be', 'm.youtube.com']):
            return 'youtube'
        return 'unknown'

    def _resolve_url(self, url: str) -> str:
        """Разворачивает короткие мобильные ссылки (vm.tiktok.com) в полные"""
        if 'vm.tiktok.com' in url.lower() or 'vt.tiktok.com' in url.lower():
            try:
                # Делаем быстрый запрос, чтобы поймать куда ведет редирект
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
                return response.url
            except Exception as e:
                logger.warning(f"Не удалось развернуть ссылку {url}: {e}")
        return url

    def _download_tiktok_api(self, url: str, progress_callback=None, loop=None) -> Dict[str, Any]:
        """Альтернативное скачивание TikTok через бесплатный API (с логированием в чат)"""
        try:
            api_url = "https://www.tikwm.com/api/"
            response = requests.post(api_url, data={"url": url, "hd": 1}, timeout=15).json()

            if response.get("code") != 0:
                return {'success': False, 'error': 'API не смог обработать ссылку TikTok'}

            info = response["data"]
            title = info.get("title", "TikTok Media")
            uploader = info.get("author", {}).get("nickname", "Unknown")

            # Внутренняя функция для отправки прогресса в Telegram
            last_update = [0.0]

            def report_progress(file_type, current_idx, total, downloaded, total_bytes, start_time):
                if not (progress_callback and loop): return

                now = time.time()
                # Обновляем сообщение раз в 1.5 сек или в самом конце скачивания файла
                if now - last_update[0] >= 1.5 or downloaded == total_bytes:
                    last_update[0] = now

                    elapsed = now - start_time
                    speed_bps = downloaded / elapsed if elapsed > 0 else 0

                    # Форматируем скорость
                    if speed_bps > 1048576:  # Больше 1 МБ/с
                        speed_str = f"{speed_bps / 1048576:.2f} MiB/s"
                    else:
                        speed_str = f"{speed_bps / 1024:.2f} KiB/s"

                    # Формируем текст в зависимости от типа файла
                    if file_type == 'photo':
                        # Для фото: убрали прогресс-бар
                        text = f"📸 **Скачивание фото {current_idx} из {total}...**\n\nСкорость: `{speed_str}`"
                    else:
                        # Для аудио: оставляем прогресс-бар
                        percent = (downloaded / total_bytes * 100) if total_bytes else 0
                        bar = make_progress_bar(percent)
                        text = f"🎵 **Скачивание аудио...**\n\n`{bar}`\nСкорость: `{speed_str}`"

                    asyncio.run_coroutine_threadsafe(progress_callback(text), loop)

            downloaded_imgs = []
            if "images" in info and info["images"]:
                urls = info["images"]
                total_imgs = len(urls)
                prefix = info.get("id", "tiktok_photo")

                # Скачиваем каждое фото с прогресс-баром
                for idx, img_url in enumerate(urls, 1):
                    start_time = time.time()
                    try:
                        resp = requests.get(img_url, stream=True, timeout=10)
                        if resp.status_code == 200:
                            total_bytes = int(resp.headers.get('content-length', 0))
                            downloaded_bytes = 0
                            out_path = os.path.join(self.download_dir, f"{prefix}_{idx}.jpg")

                            with open(out_path, 'wb') as f:
                                for chunk in resp.iter_content(chunk_size=8192):
                                    f.write(chunk)
                                    downloaded_bytes += len(chunk)
                                    report_progress('photo', idx, total_imgs, downloaded_bytes, total_bytes, start_time)

                            downloaded_imgs.append(out_path)
                    except Exception as e:
                        logger.error(f"Ошибка при скачивании картинки {img_url}: {e}")

                # === СКАЧИВАЕМ ЗВУК С ПРОГРЕСС-БАРОМ ===
                audio_path = None
                music_url = info.get("music") or info.get("music_info", {}).get("play")

                if music_url:
                    start_time = time.time()
                    try:
                        audio_resp = requests.get(music_url, stream=True, timeout=10)
                        if audio_resp.status_code == 200:
                            total_bytes = int(audio_resp.headers.get('content-length', 0))
                            downloaded_bytes = 0
                            audio_path = os.path.join(self.download_dir, f"{info.get('id', 'tiktok_audio')}.mp3")

                            with open(audio_path, 'wb') as f:
                                for chunk in audio_resp.iter_content(chunk_size=8192):
                                    f.write(chunk)
                                    downloaded_bytes += len(chunk)
                                    report_progress('audio', 1, 1, downloaded_bytes, total_bytes, start_time)
                    except Exception as e:
                        logger.warning(f"Не удалось скачать звук для карусели: {e}")

                if downloaded_imgs:
                    return {
                        'success': True,
                        'media_type': 'images',
                        'image_paths': downloaded_imgs,
                        'audio_path': audio_path,
                        'title': title,
                        'uploader': uploader,
                        'service': 'tiktok'
                    }
            return {'success': False, 'error': '❌ В этой ссылке нет фото.'}
        except Exception as e:
            logger.error(f"Ошибка TikWM API: {e}")
            return {'success': False, 'error': '❌ Ошибка при обращении к TikTok API'}

    def _download_youtube_api(self, url: str, progress_callback=None, loop=None) -> Dict[str, Any]:
        """Альтернативное скачивание YouTube через зеркала Cobalt (обход блокировок IP)"""

        # Список актуальных зеркал Cobalt, поднятых комьюнити
        cobalt_instances = [
            "https://co.wuk.sh/api/json",
            "https://cobalt.qoid.co/api/json",
            "https://api.cobalt.tools/api/json"
        ]

        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        }
        data = {
            "url": url,
            "vQuality": "720"  # Оптимально для лимита в 50 МБ
        }

        direct_url = None

        # Перебираем зеркала, пока одно из них не отдаст ссылку
        for api_url in cobalt_instances:
            try:
                response = requests.post(api_url, headers=headers, json=data, timeout=15).json()

                # Проверяем успешный ответ
                if response.get("status") != "error" and response.get("url"):
                    direct_url = response.get("url")
                    break  # Ссылка получена, прерываем цикл
            except Exception as e:
                logger.warning(f"Зеркало {api_url} не ответило: {e}")
                continue

        if not direct_url:
            return {'success': False,
                    'error': '❌ Все доступные API-серверы перегружены или недоступны. Попробуйте позже.'}

        try:
            # === Внутренняя логика прогресс-бара ===
            last_update = [0.0]

            def report_progress(downloaded, total_bytes, start_time):
                if not (progress_callback and loop): return
                now = time.time()
                if now - last_update[0] >= 1.5 or downloaded == total_bytes:
                    last_update[0] = now
                    elapsed = now - start_time
                    speed_bps = downloaded / elapsed if elapsed > 0 else 0
                    speed_str = f"{speed_bps / 1048576:.2f} MiB/s" if speed_bps > 1048576 else f"{speed_bps / 1024:.2f} KiB/s"
                    percent = (downloaded / total_bytes * 100) if total_bytes else 0
                    bar = make_progress_bar(percent)
                    text = f"🎥 **Скачивание видео...**\n\n`{bar}`\nСкорость: `{speed_str}`"
                    asyncio.run_coroutine_threadsafe(progress_callback(text), loop)

            # === Скачиваем сам файл ===
            video_id = url.split('v=')[-1][:11] if 'v=' in url else 'youtube_video'
            out_path = os.path.join(self.download_dir, f"{video_id}.mp4")
            start_time = time.time()

            dl_resp = requests.get(direct_url, stream=True, timeout=20)
            if dl_resp.status_code == 200:
                total_bytes = int(dl_resp.headers.get('content-length', 0))
                downloaded_bytes = 0

                with open(out_path, 'wb') as f:
                    for chunk in dl_resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded_bytes += len(chunk)
                        report_progress(downloaded_bytes, total_bytes, start_time)

                file_size = os.path.getsize(out_path)
                if file_size > 50 * 1024 * 1024:
                    os.remove(out_path)
                    return {'success': False, 'error': 'Файл слишком большой для отправки в Telegram (более 50 МБ)'}

                return {
                    'success': True,
                    'media_type': 'video',
                    'file_path': out_path,
                    'title': "YouTube Video",
                    'uploader': "YouTube",
                    'duration': 0,
                    'service': 'youtube'
                }
            return {'success': False, 'error': '❌ Ошибка при загрузке видео по готовой ссылке'}

        except Exception as e:
            logger.error(f"Ошибка скачивания через API: {e}")
            return {'success': False, 'error': '❌ Ошибка сети при скачивании видео'}


    def _get_ydl_opts(self) -> dict:
        return {
            # Убираем жесткие ограничения по расширениям — качаем лучшее качество
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': f'{self.download_dir}/%(id)s.%(ext)s',
            #'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'merge_output_format': 'mp4',
            'headers': {
                'Referer': 'https://www.tiktok.com/',
                'Origin': 'https://www.tiktok.com',
            },
            'sleep_interval_requests': 1,
            'extractor_args': {
                'youtube': {
                    'player_client': ['tv', 'ios'],
                },
                'tiktok': {
                    'language': 'en',
                    'country': 'US',
                },
            }
        }

    async def download_media(self, url: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Универсальное скачивание видео/изображений с TikTok и YouTube с поддержкой прогресс-бара"""
        full_url = await asyncio.to_thread(self._resolve_url, url)

        # Умная очистка URL
        if 'youtube.com/watch' in full_url.lower():
            clean_url = full_url.split('&')[0]
        else:
            clean_url = full_url.split('?')[0]

        service = self.get_service_type(clean_url)

        # === ПЕРЕХВАТ TIKTOK ФОТО ===
        if service == 'tiktok' and '/photo/' in clean_url.lower():
            loop = asyncio.get_running_loop()
            return await asyncio.to_thread(self._download_tiktok_api, clean_url, progress_callback, loop)

        if service == 'youtube':
            loop = asyncio.get_running_loop()
            return await asyncio.to_thread(self._download_youtube_api, clean_url, progress_callback, loop)
        # === ЛОГИКА ДЛЯ ОСТАЛЬНЫХ ССЫЛОК (через yt-dlp) ===
        opts = self._get_ydl_opts()
        loop = asyncio.get_running_loop()
        last_update = [0.0]

        def ytdl_hook(d):
            if d.get('status') == 'downloading':
                now = time.time()
                # Ограничиваем частоту вызовов прогресс-бара (раз в 1.5 сек), чтобы не забанил Telegram API
                if now - last_update[0] >= 1.5:
                    last_update[0] = now
                    total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                    downloaded = d.get('downloaded_bytes') or 0
                    percent = (downloaded / total * 100) if total > 0 else 0

                    speed_raw = d.get('_speed_str', 'N/A')
                    eta_raw = d.get('_eta_str', 'N/A')

                    speed = re.sub(r'\x1b\[[0-9;]*m', '', speed_raw).strip() if isinstance(speed_raw, str) else 'N/A'
                    eta = re.sub(r'\x1b\[[0-9;]*m', '', eta_raw).strip() if isinstance(eta_raw, str) else 'N/A'

                    if progress_callback:
                        asyncio.run_coroutine_threadsafe(
                            progress_callback(percent, speed, eta),
                            loop
                        )

        opts['progress_hooks'] = [ytdl_hook]

        try:
            # Передаем очищенный clean_url в _sync_download
            return await asyncio.to_thread(self._sync_download, clean_url, opts, service)
        except Exception as e:
            logger.error(f"Ошибка скачивания медиа: {e}", exc_info=True)
            return {
                'success': False,
                'error': f'Произошла ошибка при скачивании: {str(e)}'
            }


    def _sync_download(self, url: str, opts: dict, service: str) -> Dict[str, Any]:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return {'success': False, 'error': 'Не удалось получить информацию по ссылке'}

                title = info.get('title', 'Media')
                uploader = info.get('uploader', 'Unknown')
                duration = info.get('duration', 0)

                # 1. Проверяем наличие слайдшоу/картинок (TikTok photos)
                image_paths = []
                
                if 'entries' in info and info['entries']:
                    for entry in info['entries']:
                        if not entry:
                            continue
                        filename = ydl.prepare_filename(entry)
                        if os.path.exists(filename):
                            ext = os.path.splitext(filename)[1].lower()
                            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                image_paths.append(filename)

                if not image_paths and 'requested_downloads' in info:
                    for req in info['requested_downloads']:
                        fp = req.get('filepath')
                        if fp and os.path.exists(fp):
                            ext = os.path.splitext(fp)[1].lower()
                            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                                image_paths.append(fp)

                single_filename = ydl.prepare_filename(info)
                if not image_paths and os.path.exists(single_filename):
                    ext = os.path.splitext(single_filename)[1].lower()
                    if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                        image_paths.append(single_filename)

                if image_paths:
                    return {
                        'success': True,
                        'media_type': 'images',
                        'image_paths': image_paths,
                        'title': title,
                        'uploader': uploader,
                        'service': service
                    }

                if not image_paths and info.get('images'):
                    downloaded_imgs = self._download_image_urls(info['images'], info.get('id', 'photo'))
                    if downloaded_imgs:
                        return {
                            'success': True,
                            'media_type': 'images',
                            'image_paths': downloaded_imgs,
                            'title': title,
                            'uploader': uploader,
                            'service': service
                        }

                # 2. Если это видео файл
                if not os.path.exists(single_filename):
                    media_id = info.get('id')
                    found_file = None
                    for fname in os.listdir(self.download_dir):
                        if media_id and media_id in fname:
                            found_file = os.path.join(self.download_dir, fname)
                            break
                    if found_file:
                        single_filename = found_file
                    else:
                        return {'success': False, 'error': 'Файл не найден после скачивания.'}

                file_size = os.path.getsize(single_filename)
                if file_size > 50 * 1024 * 1024:
                    os.remove(single_filename)
                    return {
                        'success': False,
                        'error': 'Файл слишком большой для отправки в Telegram (более 50 МБ)'
                    }

                return {
                    'success': True,
                    'media_type': 'video',
                    'file_path': single_filename,
                    'title': title,
                    'uploader': uploader,
                    'duration': duration,
                    'service': service
                }


        except yt_dlp.utils.DownloadError as e:

            logger.error(f"Ошибка yt-dlp: {e}")

            err_msg = str(e)
            clean_err = re.sub(r'\x1b\[[0-9;]*m', '', err_msg)
            clean_err = clean_err.replace('ERROR:', '').strip()

            if 'sigi state' in clean_err.lower():
                return {'success': False, 'error': '❌ TikTok изменил структуру страницы, попробуйте другую ссылку.'}

            return {'success': False, 'error': f'❌ Ошибка скачивания:\n{clean_err}'}

    def _download_image_urls(self, urls: List[str], prefix: str) -> List[str]:
        downloaded = []
        for idx, img_url in enumerate(urls):
            try:
                resp = requests.get(img_url, timeout=10)
                if resp.status_code == 200:
                    out_path = os.path.join(self.download_dir, f"{prefix}_{idx}.jpg")
                    with open(out_path, 'wb') as f:
                        f.write(resp.content)
                    downloaded.append(out_path)
            except Exception as e:
                logger.error(f"Ошибка при скачивании картинки {img_url}: {e}")
        return downloaded


TikTokDownloader = MediaDownloader
