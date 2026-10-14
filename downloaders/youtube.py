import os
from .base import BaseDownloader


class YoutubeDownloader(BaseDownloader):
    def get_ydl_opts(self) -> dict:
        opts = {
            'outtmpl': f'{self.download_dir}/%(id)s.%(ext)s',
            'quiet': False,
            'merge_output_format': 'mp4',
            'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
            'js_runtimes': {'deno': {}, 'node': {}},
        }

        for cookie_path in ['/etc/secrets/cookies.txt', 'cookies.txt']:
            if os.path.exists(cookie_path) and os.path.getsize(cookie_path) > 0:
                opts['cookiefile'] = cookie_path
                break

        return opts