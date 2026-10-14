from .base import BaseDownloader
import os


class YoutubeDownloader(BaseDownloader):
    def get_ydl_opts(self) -> dict:
        opts = {
            'outtmpl': f'{self.download_dir}/%(id)s.%(ext)s',
            'quiet': False,
            'merge_output_format': 'mp4',
            'format': 'bestvideo[height<=1080][filesize<40M]+bestaudio[filesize<10M]/best[height<=1080][filesize<50M]/best[height<=720]',
            'extractor_args': {
                'youtube': {
                    'player_client': ['web', 'mweb', 'ios']
                }
            },
        }

        # Автоматически подцепляем cookies.txt, если он есть в проекте
        for cookie_path in ['/etc/secrets/cookies.txt', 'cookies.txt']:
            if os.path.exists(cookie_path) and os.path.getsize(cookie_path) > 0:
                opts['cookiefile'] = cookie_path
                break

        return opts