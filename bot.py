import asyncio
import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    InlineQueryHandler,
    ChosenInlineResultHandler,
    filters
)
from telegram.request import HTTPXRequest

from config import BOT_TOKEN
import database
from web_server import start_web_server
from handlers.commands import start, history, stats, raupov, help_command
from handlers.inline import inline_query, chosen_inline_result
from handlers.web_app import handle_web_app_data
from handlers.messages import handle_message

logger = logging.getLogger(__name__)


async def post_init(application: Application):
    """Инициализация БД и веб-сервера при запуске бота"""
    await database.init_db()
    logger.info("База данных инициализирована")

    asyncio.create_task(start_web_server())


def main():
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=10.0
    )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .build()
    )

    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("raupov", raupov))
    application.add_handler(CommandHandler("help", help_command))

    # Регистрация инлайн обработчиков
    application.add_handler(InlineQueryHandler(inline_query))
    application.add_handler(ChosenInlineResultHandler(chosen_inline_result))

    bot_mention = filters.Mention("@gruzdtbot")
    group_filter = (
            filters.TEXT &
            ~filters.COMMAND &
            (bot_mention | filters.REPLY)
    )

    # Регистрация обработчика WebApp
    application.add_handler(MessageHandler(group_filter, handle_message))

    # Обработчик текстовых сообщений (ссылки TikTok и YouTube)
    application.add_handler(MessageHandler(group_filter, handle_message))

    logger.info("Бот запущен!")
    application.run_polling()


if __name__ == '__main__':
    main()
