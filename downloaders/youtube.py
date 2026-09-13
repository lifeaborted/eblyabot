from .base import BaseDownloader

class YoutubeDownloader(BaseDownloader):
    def get_ydl_opts(self) -> dict:
        return {
            'outtmpl': f'{self.download_dir}/%(id)s.%(ext)s',
            'proxy': 'socks5://127.0.0.1:1080',  # Прокси применяется только для YouTube
            'quiet': False,
            'merge_output_format': 'mp4',
            'extractor_args': {'youtube': {'player_client': ['android_vr', 'ios', 'android', 'tv']}},
        }