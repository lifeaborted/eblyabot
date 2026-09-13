import logging
import sys
from logging.handlers import TimedRotatingFileHandler


def setup_global_logger():
    # Получаем корневой (Root) логер
    root_logger = logging.getLogger()

    # Очищаем дефолтные хендлеры, чтобы избежать дублирования (важно!)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Файловый хендлер (ротация)
    file_handler = TimedRotatingFileHandler(
        filename='bot.log',
        when='midnight',
        interval=1,
        backupCount=1,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)

    # Консольный хендлер
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Привязываем хендлеры к корневому логеру
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)