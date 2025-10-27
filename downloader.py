import yt_dlp
import os
import logging
from pathlib import Path

# Папка для постоянного хранения файлов
<<<<<<< HEAD
DOWNLOAD_DIR = 'downloads'
=======
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', '/var/task/downloads')
>>>>>>> c4e063a (я докер поднял)
Path(DOWNLOAD_DIR).mkdir(exist_ok=True)

logger = logging.getLogger(__name__)


class TikTokDownloader:
    def __init__(self):
        self.ydl_opts = {
            'format': 'best',
            'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

    async def download_video(self, url: str) -> dict:
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                # Получаем информацию о видео
                info = ydl.extract_info(url, download=True)

                # Путь к скачанному файлу
                file_path = ydl.prepare_filename(info)

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
            logger.error(f"Ошибка скачивания: {e}")
            return {
                'success': False,
                'error': 'Не удалось скачать видео. Возможно, оно недоступно или удалено.'
            }
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {e}")

    @staticmethod
    def file_exists(file_path: str) -> bool:
        """Проверка существования файла"""
<<<<<<< HEAD
        return os.path.exists(file_path) if file_path else False
=======
        return os.path.exists(file_path) if file_path else False
>>>>>>> c4e063a (я докер поднял)
