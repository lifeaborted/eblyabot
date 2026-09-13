import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
import database
from web_server import start_web_server
from utils.logger import setup_global_logger

# Создаем локальный логер стандартным способом
logger = logging.getLogger(__name__)

from handlers.commands import router as commands_router
from handlers.inline import router as inline_router
from handlers.messages import router as messages_router
from handlers.web_app import router as webapp_router

async def main():
    await database.init_db()
    logger.info("База данных инициализирована")
    asyncio.create_task(start_web_server())

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
    dp = Dispatcher()

    dp.include_router(commands_router)
    dp.include_router(inline_router)
    dp.include_router(webapp_router)
    dp.include_router(messages_router)

    logger.info("Бот запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    # ВАЖНО: Вызов настройки логера самым первым
    setup_global_logger()
    asyncio.run(main())