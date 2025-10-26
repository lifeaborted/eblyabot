import yt_dlp
import os
import logging
from pathlib import Path

# Папка для временных файлов
DOWNLOAD_DIR = 'downloads'
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
        """
        Скачивание видео из TikTok

        Returns:
            dict: {
                'success': bool,
                'file_path': str,
                'title': str,
                'error': str (если есть)
            }
        """
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
            return {
                'success': False,
                'error': f'Произошла ошибка: {str(e)}'
            }

    @staticmethod
    def cleanup_file(file_path: str):
        """Удаление файла после отправки"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Файл {file_path} удален")
        except Exception as e:
            logger.error(f"Ошибка при удалении файла: {e}")