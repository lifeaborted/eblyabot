import asyncio
import os
import re
from .youtube import YoutubeDownloader
from .tiktok_video import TiktokVideoDownloader
from .tiktok_slideshow import TiktokSlideshowDownloader
from .instagram import InstagramDownloader

download_semaphore = asyncio.Semaphore(1)


async def download_media(downloader, url, progress_callback=None):
    async with download_semaphore:
        task = asyncio.create_task(downloader.download(url, progress_callback=progress_callback))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # The worker thread continues after cancellation, so hold the slot and remove its files.
            try:
                result = await task
            except Exception:
                pass
            else:
                paths = [result.get('file_path'), result.get('audio_path'), result.get('thumbnail_path')]
                paths.extend(result.get('image_paths', []))
                for path in paths:
                    if path and os.path.exists(path):
                        os.remove(path)
            raise

class DownloaderFactory:
    @staticmethod
    def get(url: str, download_dir: str):
        if re.search(r'(youtube\.com|youtu\.be)', url, re.IGNORECASE):
            return YoutubeDownloader(download_dir)
        elif re.search(r'(tiktok\.com|tt\.site)', url, re.IGNORECASE):
            if '/photo/' in url.lower():
                return TiktokSlideshowDownloader(download_dir)
            else:
                return TiktokVideoDownloader(download_dir)
        elif re.search(r'(instagram\.com|ig\.me)', url, re.IGNORECASE):
            return InstagramDownloader(download_dir)
        return None
