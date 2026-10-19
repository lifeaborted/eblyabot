import asyncio
import os
import re
import json
import requests
from curl_cffi import requests as cffi_requests
import logging
import subprocess
import uuid
from typing import Optional, Callable
from .base import BaseDownloader

logger = logging.getLogger(__name__)


class TiktokSlideshowDownloader(BaseDownloader):
    def get_ydl_opts(self) -> dict:
        return {}

    def _fix_image(self, img_path: str) -> bool:
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
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=15)
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 1024:
                os.replace(tmp_path, img_path)
                return True
            else:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                return False
        except Exception as e:
            logger.warning(f"Ошибка конвертации изображения {img_path}: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return False

    def _stitch_video(self, image_path: str, audio_path: str, video_id: str, run_id: str) -> str:
        output_path = os.path.join(self.download_dir, f"tt_stitch_{video_id}_{run_id}.mp4")
        cmd = [
            'ffmpeg', '-y',
            '-threads', '1',
            '-loop', '1', '-framerate', '1',
            '-i', image_path,
            '-i', audio_path,
            '-vf', "scale='min(1080,iw)':-2",
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'stillimage',
            '-c:a', 'aac', '-b:a', '128k',
            '-pix_fmt', 'yuv420p',
            '-shortest',
            '-fflags', '+shortest',
            '-max_interleave_delta', '100M',
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=45)
        return output_path

    async def download(self, url: str, progress_callback: Optional[Callable] = None):
        return await asyncio.to_thread(self._sync_download_slideshow, url)

    def _sync_download_slideshow(self, url: str):
        video_id_match = re.search(r'/(?:photo|video)/(\d+)', url)
        video_id = video_id_match.group(1) if video_id_match else "unknown"
        run_id = uuid.uuid4().hex[:6]

        active_proxies = self.proxies
        images, audio, author, title = self._get_data(url, active_proxies)

        if not images:
            return {'success': False, 'error': 'Не удалось получить фотографии. Возможно, пост приватный.'}

        downloaded_imgs = []
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36',
            'Referer': 'https://www.tiktok.com/'
        }

        for idx, img_url in enumerate(images, 1):
            try:
                r = requests.get(img_url, headers=headers, proxies=active_proxies, timeout=15)
                if r.status_code == 200 and len(r.content) > 1024:
                    path = os.path.join(self.download_dir, f"tt_{video_id}_{run_id}_{idx}.jpg")
                    with open(path, 'wb') as f:
                        f.write(r.content)

                    if self._fix_image(path):
                        downloaded_imgs.append(path)
                    else:
                        if os.path.exists(path):
                            os.remove(path)
                else:
                    logger.warning(f"Фото {idx} не скачано. Код: {r.status_code}")
            except Exception as e:
                logger.error(f"Ошибка скачивания фото {idx}: {e}")

        if not downloaded_imgs:
            return {'success': False, 'error': 'Не удалось обработать ни одну фотографию.'}

        audio_path = None
        if audio:
            try:
                r = requests.get(audio, headers=headers, proxies=active_proxies, timeout=15)
                if r.status_code == 200 and len(r.content) > 1024:
                    audio_path = os.path.join(self.download_dir, f"tt_{video_id}_{run_id}.mp3")
                    with open(audio_path, 'wb') as f:
                        f.write(r.content)
            except Exception as e:
                logger.error(f"Ошибка скачивания аудио: {e}")

        if len(downloaded_imgs) == 1 and audio_path and os.path.exists(audio_path):
            try:
                video_path = self._stitch_video(downloaded_imgs[0], audio_path, video_id, run_id)
                thumb_path = self._generate_thumbnail(video_path)
                if os.path.exists(downloaded_imgs[0]):
                    os.remove(downloaded_imgs[0])
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                return {
                    'success': True,
                    'media_type': 'video',
                    'file_path': video_path,
                    'thumbnail_path': thumb_path,
                    'title': title,
                    'uploader': author,
                    'description': title
                }
            except Exception as e:
                logger.error(f"Ошибка склейки видео: {e}. Отдаю как фото + аудио.")

        return {
            'success': True,
            'media_type': 'images',
            'image_paths': downloaded_imgs,
            'audio_path': audio_path,
            'title': title,
            'uploader': author,
            'description': title
        }

    def _get_data(self, url: str, active_proxies: Optional[dict]):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

        logger.info("Попытка 1: Парсим оригинальный HTML TikTok через curl_cffi...")
        try:
            resp = cffi_requests.get(
                url,
                headers=headers,
                proxies=active_proxies,
                impersonate="chrome",
                timeout=15,
                allow_redirects=True
            )

            match = re.search(
                r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
                resp.text,
                re.DOTALL
            )
            if match:
                data = json.loads(match.group(1))
                video_detail = data.get('__DEFAULT_SCOPE__', {}).get('webapp.video-detail', {})
                item = video_detail.get('itemInfo', {}).get('itemStruct', {}) or video_detail.get('itemInfo', {})

                images = []
                if item.get('imagePost') and item['imagePost'].get('images'):
                    images = [
                        img['imageURL']['urlList'][0]
                        for img in item['imagePost']['images']
                        if img.get('imageURL') and img['imageURL'].get('urlList')
                    ]

                audio = item.get('music', {}).get('playUrl')
                author = item.get('author', 'Unknown')
                if isinstance(author, dict):
                    author = author.get('nickname') or author.get('uniqueId') or 'Unknown'
                desc = item.get('desc', '')

                if images:
                    logger.info("Успех: Данные получены через HTML-парсер (REHYDRATION).")
                    return images, audio, author, desc

            match_sigi = re.search(r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', resp.text, re.DOTALL)
            if match_sigi:
                data = json.loads(match_sigi.group(1))
                item_module = data.get('ItemModule', {})
                if item_module:
                    first_key = list(item_module.keys())[0]
                    item = item_module[first_key]

                    images = []
                    if item.get('imagePost') and item['imagePost'].get('images'):
                        images = [
                            img['imageURL']['urlList'][0]
                            for img in item['imagePost']['images']
                            if img.get('imageURL') and img['imageURL'].get('urlList')
                        ]

                    audio = item.get('music', {}).get('playUrl')
                    author = item.get('author', 'Unknown')
                    desc = item.get('desc', '')

                    if images:
                        logger.info("Успех: Данные получены через HTML-парсер (SIGI_STATE).")
                        return images, audio, author, desc

            logger.warning("Собственный парсер не нашел данных. Переключаюсь на резервный API.")
        except Exception as e:
            logger.warning(f"Ошибка при работе собственного парсера HTML: {e}")

        logger.info("Попытка 2: Переход на резервный API (TikWM)...")
        try:
            resp = requests.post(
                "https://www.tikwm.com/api/",
                data={"url": url, "hd": 1},
                headers={'User-Agent': headers['User-Agent']},
                proxies=active_proxies,
                timeout=15
            )
            if resp.status_code == 200:
                resp_json = resp.json()
                if resp_json.get("code") == 0:
                    data = resp_json.get("data", {})
                    if data.get("images"):
                        logger.info("Успех: Данные получены через TikWM.")
                        return (
                            data["images"],
                            data.get("music", ""),
                            data.get("author", {}).get("nickname", "Unknown"),
                            data.get("title", "")
                        )
            else:
                logger.warning(f"Резервный API TikWM вернул статус-код: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Сбой подключения к резервному API TikWM: {e}")

        return None, None, None, None