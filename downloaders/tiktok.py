import time
import requests
import asyncio
import os
from .base import BaseDownloader
import logging
logger = logging.getLogger(__name__)


class TiktokDownloader(BaseDownloader):
    def get_ydl_opts(self) -> dict:
        return {
            'outtmpl': f'{self.download_dir}/%(id)s.%(ext)s',
            'quiet': False,
            'merge_output_format': 'mp4',
            # Без прокси, TikTok качается напрямую
            'extractor_args': {'tiktok': {'language': 'en', 'country': 'US'}},
        }

    async def download(self, url: str, progress_callback=None):
        if '/photo/' in url.lower():
            # Перехват TikTok фото-слайдшоу через внешний API TikWM (как было в оригинале)
            loop = asyncio.get_running_loop()
            return await asyncio.to_thread(self._download_tiktok_api, url, progress_callback, loop)
        return await super().download(url, progress_callback)

    def _download_tiktok_api(self, url: str, progress_callback, loop) -> dict:
        try:
            resp = requests.post("https://www.tikwm.com/api/", data={"url": url, "hd": 1}, timeout=15).json()
            if resp.get("code") != 0: return {'success': False, 'error': 'API Error'}

            info = resp["data"]
            downloaded_imgs = []
            audio_path = None

            if "images" in info:
                for idx, img_url in enumerate(info["images"], 1):
                    r = requests.get(img_url, stream=True, timeout=10)
                    if r.status_code == 200:
                        path = os.path.join(self.download_dir, f"{info.get('id', 'tt')}_{idx}.jpg")
                        with open(path, 'wb') as f: f.write(r.content)
                        downloaded_imgs.append(path)

            music_url = info.get("music") or info.get("music_info", {}).get("play")
            if music_url:
                r = requests.get(music_url, stream=True, timeout=10)
                if r.status_code == 200:
                    audio_path = os.path.join(self.download_dir, f"{info.get('id', 'tt')}.mp3")
                    with open(audio_path, 'wb') as f: f.write(r.content)

            return {
                'success': True, 'media_type': 'images', 'image_paths': downloaded_imgs,
                'audio_path': audio_path, 'title': info.get("title", "Media"),
                'uploader': info.get("author", {}).get("nickname")
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}