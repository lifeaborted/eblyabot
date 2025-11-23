import yt_dlp
import os
import logging
from pathlib import Path

# Папка для постоянного хранения файлов
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads_main')

logger = logging.getLogger(__name__)


class TikTokDownloader:
    def __init__(self):
        self.ydl_opts = {
            'format': 'best',
            'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
            'quiet': False,  # Changed to False to see detailed logs
            'no_warnings': False,  # Changed to False to see warnings
            'extract_flat': False,
            'verbose': True,  # Added for more detailed logs
            # TikTok-specific options to handle API changes
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'headers': {
                'Referer': 'https://www.tiktok.com/',
                'Origin': 'https://www.tiktok.com',
            },
            'sleep_interval_requests': 1,  # Add a small delay between requests
            'extractor_args': {
                'youtube': {
                    'skip': ['hls', 'dash'],
                },
                'tiktok': {
                    'language': 'en',
                    'country': 'US',
                },
            }
        }

    async def download_video(self, url: str) -> dict:
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                # Проверяем URL на корректность
                if 'tiktok.com' not in url.lower() and 'vm.tiktok.com' not in url.lower() and 'vt.tiktok.com' not in url.lower():
                    return {
                        'success': False,
                        'error': 'Неверная ссылка. Поддерживаются только TikTok ссылки.'
                    }

                # Получаем информацию о видео
                info = ydl.extract_info(url, download=True)

                # Путь к скачанному файлу
                file_path = ydl.prepare_filename(info)

                # Проверяем, что файл действительно существует
                if not os.path.exists(file_path):
                    logger.error(f"Файл не был создан по пути: {file_path}")
                    return {
                        'success': False,
                        'error': 'Не удалось создать файл видео'
                    }

                # Получаем размер файла
                file_size = os.path.getsize(file_path)

                # Telegram поддерживает файлы до 50 МБ для ботов
                if file_size > 50 * 1024 * 1024:
                    os.remove(file_path)
                    return {
                        'success': False,
                        'error': 'Файл слишком большой (более 50 МБ)'
                    }

                return {
                    'success': True,
                    'file_path': file_path,
                    'title': info.get('title', 'TikTok Video'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                }

        except yt_dlp.utils.DownloadError as e:
            logger.error(f"Ошибка скачивания yt-dlp: {e}")
            # Check if the error is related to TikTok API changes
            if 'sigi state' in str(e) or 'extractor' in str(e):
                return {
                    'success': False,
                    'error': 'Не удалось скачать видео. TikTok изменил API, используйте другую ссылку или подождите обновления.'
                }
            else:
                return {
                    'success': False,
                    'error': f'Не удалось скачать видео: {str(e)}'
                }
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")
            return {
                'success': False,
                'error': f'Произошла непредвиденная ошибка: {str(e)}'
            }
