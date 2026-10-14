from .base import BaseDownloader

class TiktokVideoDownloader(BaseDownloader):
    def get_ydl_opts(self) -> dict:
        return {
            'outtmpl': f'{self.download_dir}/%(id)s.%(ext)s',
            'quiet': False,
            'merge_output_format': 'mp4',
            'extractor_args': {'tiktok': {'language': 'en', 'country': 'US'}},
        }