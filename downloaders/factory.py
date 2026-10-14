import re
from .youtube import YoutubeDownloader
from .tiktok_video import TiktokVideoDownloader
from .tiktok_slideshow import TiktokSlideshowDownloader
from .instagram import InstagramDownloader

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