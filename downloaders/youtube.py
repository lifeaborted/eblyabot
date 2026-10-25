import os
from .base import BaseDownloader

os.environ.setdefault("NODE_OPTIONS", "--max-old-space-size=64")


class YoutubeDownloader(BaseDownloader):
    def get_ydl_opts(self) -> dict:
        opts = {
            'outtmpl': f'{self.download_dir}/%(id)s.%(ext)s',
            'quiet': False,
            'merge_output_format': 'mp4',
            'format': (
                'bestvideo[height<=1080][filesize<40M]+bestaudio[filesize<10M]/'
                'bestvideo[height<=720][filesize<40M]+bestaudio/'
                'best[height<=720]/best'
            ),
            'js_runtimes': {'node': {}, 'deno': {}},
        }

        for cookie_path in ['/etc/secrets/cookies.txt', 'cookies.txt']:
            if os.path.exists(cookie_path) and os.path.getsize(cookie_path) > 0:
                opts['cookiefile'] = cookie_path
                break

        return opts