import re
from .youtube import YoutubeDownloader
from .tiktok import TiktokDownloader

class DownloaderFactory:
    @staticmethod
    def get(url: str, download_dir: str):
        if re.search(r'(youtube\.com|youtu\.be)', url, re.IGNORECASE):
            return YoutubeDownloader(download_dir)
        elif re.search(r'(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)', url, re.IGNORECASE):
            return TiktokDownloader(download_dir)
        return None