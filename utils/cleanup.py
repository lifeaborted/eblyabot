import os
import asyncio
from contextlib import asynccontextmanager
import logging
logger = logging.getLogger(__name__)


@asynccontextmanager
async def temp_files_cleanup(file_paths: list[str]):
    """Асинхронный контекстный менеджер для гарантированного удаления скачанных файлов"""
    try:
        yield
    finally:
        for path in file_paths:
            if path and os.path.exists(path):
                try:
                    await asyncio.to_thread(os.remove, path)
                    logger.info(f"Удален локальный файл: {path}")
                except Exception as e:
                    logger.error(f"Ошибка удаления файла {path}: {e}")