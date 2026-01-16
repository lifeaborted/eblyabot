import os
import logging
import asyncio
import hashlib
from pathlib import Path
from typing import Dict, Optional
from tiktok_downloader import snaptik, tikmate, mdown

DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', 'downloads_main')
logger = logging.getLogger(__name__)


class TikTokDownloader:
    def __init__(self):
        """Инициализация загрузчика TikTok"""
        Path(DOWNLOAD_DIR).mkdir(exist_ok=True)
        logger.info(f"TikTok Downloader initialized. Download dir: {DOWNLOAD_DIR}")

        # Порядок попыток сервисов (если один не работает, пробуем другой)
        self.services = [snaptik, tikmate, mdown]
        self.current_service = 0

    async def download_video(self, url: str) -> Dict:
        """
        Скачивание TikTok видео через обходные сервисы

        Args:
            url: Ссылка на TikTok видео

        Returns:
            dict: {
                'success': bool,
                'file_path': str (если success=True),
                'title': str,
                'uploader': str,
                'error': str (если success=False)
            }
        """
        try:
            if 'tiktok.com' not in url.lower():
                return {
                    'success': False,
                    'error': 'Неверная ссылка. Поддерживаются только TikTok ссылки.'
                }

            logger.info(f"Начало скачивания: {url}")

            # Пробуем скачать через доступные сервисы
            for attempt, service in enumerate(self.services, 1):
                try:
                    logger.info(f"Попытка {attempt}/{len(self.services)} через {service.__name__}")
                    result = await self._download_with_service(url, service)

                    if result['success']:
                        logger.info(f"✅ Успешно скачано через {service.__name__}")
                        return result
                    else:
                        logger.warning(f"⚠️ {service.__name__} не сработал: {result.get('error')}")

                except Exception as e:
                    logger.error(f"❌ Ошибка в {service.__name__}: {e}")
                    continue

            # Если все сервисы не сработали
            return {
                'success': False,
                'error': 'Не удалось скачать видео. TikTok может быть недоступен или видео удалено.'
            }

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}", exc_info=True)
            return {
                'success': False,
                'error': f'Ошибка: {str(e)}'
            }

    async def _download_with_service(self, url: str, service) -> Dict:
        """
        Скачивание через конкретный сервис

        Args:
            url: Ссылка на видео
            service: Функция сервиса (snaptik, tikmate, mdown)
        """
        try:
            # Запускаем в отдельном потоке, так как библиотека синхронная
            loop = asyncio.get_event_loop()
            videos = await loop.run_in_executor(None, service, url)

            if not videos or len(videos) == 0:
                return {
                    'success': False,
                    'error': 'Видео не найдено'
                }

            # Берем первое видео (обычно без водяного знака)
            video = videos[0]

            # Генерируем уникальное имя файла на основе URL
            video_id = hashlib.md5(url.encode()).hexdigest()[:12]
            file_path = os.path.join(DOWNLOAD_DIR, f'{video_id}.mp4')

            # Скачиваем видео в файл
            logger.info(f"Сохранение видео в {file_path}")
            await loop.run_in_executor(None, video.download, file_path)

            # Проверяем что файл создан
            if not os.path.exists(file_path):
                return {
                    'success': False,
                    'error': 'Файл не был создан'
                }

            file_size = os.path.getsize(file_path)

            # Проверяем размер (Telegram лимит 50 МБ)
            if file_size > 50 * 1024 * 1024:
                os.remove(file_path)
                return {
                    'success': False,
                    'error': 'Файл слишком большой (более 50 МБ)'
                }

            if file_size < 1024:  # Меньше 1 КБ - вероятно ошибка
                os.remove(file_path)
                return {
                    'success': False,
                    'error': 'Файл слишком маленький, возможно ошибка скачивания'
                }

            logger.info(f"✅ Видео скачано: {file_path} ({file_size / (1024 * 1024):.2f} МБ)")

            # Пытаемся извлечь метаданные (может не работать для всех сервисов)
            title = self._extract_title(video, url)
            uploader = self._extract_uploader(video, url)

            return {
                'success': True,
                'file_path': file_path,
                'title': title,
                'uploader': uploader,
                'duration': 0  # Библиотека не предоставляет длительность
            }

        except Exception as e:
            logger.error(f"Ошибка в _download_with_service: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _extract_title(self, video, url: str) -> str:
        """Извлечение названия видео"""
        try:
            # Пытаемся получить title из объекта video
            if hasattr(video, 'title'):
                return video.title
            elif hasattr(video, 'json') and 'title' in video.json:
                return video.json['title']
            else:
                # Fallback: извлекаем из URL
                return f"TikTok Video {url.split('/')[-1][:10]}"
        except:
            return "TikTok Video"

    def _extract_uploader(self, video, url: str) -> str:
        """Извлечение имени автора"""
        try:
            if hasattr(video, 'author'):
                return video.author
            elif hasattr(video, 'json') and 'author' in video.json:
                return video.json['author']
            else:
                # Пытаемся извлечь из URL (формат: /@username/video/...)
                parts = url.split('/')
                for i, part in enumerate(parts):
                    if part.startswith('@'):
                        return part[1:]  # Убираем @
                return "Unknown"
        except:
            return "Unknown"

    def cleanup_old_files(self, max_files: int = 100):
        """
        Очистка старых файлов (опционально, для экономии места)

        Args:
            max_files: Максимальное количество файлов в папке
        """
        try:
            download_path = Path(DOWNLOAD_DIR)
            files = sorted(
                download_path.glob('*.mp4'),
                key=lambda f: f.stat().st_mtime,
                reverse=True
            )

            # Удаляем файлы сверх лимита
            for old_file in files[max_files:]:
                old_file.unlink()
                logger.info(f"Удален старый файл: {old_file}")

        except Exception as e:
            logger.error(f"Ошибка при очистке файлов: {e}")
