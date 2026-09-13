import re
from .youtube import YoutubeDownloader
from .tiktok_video import TiktokVideoDownloader
from .tiktok_slideshow import TiktokSlideshowDownloader

class DownloaderFactory:
    @staticmethod
    def get(url: str, download_dir: str):
        if re.search(r'(youtube\.com|youtu\.be)', url, re.IGNORECASE):
            return YoutubeDownloader(download_dir)
        elif re.search(r'tiktok\.com', url, re.IGNORECASE):
            if '/photo/' in url.lower():
                return TiktokSlideshowDownloader(download_dir)
            else:
                return TiktokVideoDownloader(download_dir)
        return None