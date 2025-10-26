import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import database
from downloader import TikTokDownloader

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Проверка токена
BOT_TOKEN = "8253639704:AAGZyIusjDMMKfNvDl3eEjSLGhzyynp-Xu0"
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден! Проверьте файл .env")

# Инициализация загрузчика
downloader = TikTokDownloader()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    await update.message.reply_text(
        f'Привет, {user.first_name}! 👋\n\n'
        '🎵 Отправь мне ссылку на TikTok видео, и я скачаю его для тебя!\n\n'
        '📋 Доступные команды:\n'
        '/start - начать работу\n'
        '/history - твоя история скачиваний\n'
        '/stats - статистика\n'
        '/help - помощь'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        '❓ Как использовать бота:\n\n'
        '1️⃣ Найди видео в TikTok\n'
        '2️⃣ Нажми "Поделиться" → "Копировать ссылку"\n'
        '3️⃣ Отправь ссылку мне\n'
        '4️⃣ Получи видео!\n\n'
        '⚠️ Ограничения:\n'
        '• Максимальный размер файла: 50 МБ\n'
        '• Только публичные видео\n\n'
        '💡 Поддерживаются ссылки вида:\n'
        '• https://www.tiktok.com/@user/video/123...\n'
        '• https://vm.tiktok.com/...'
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    url = update.message.text.strip()
    user = update.effective_user

    # Проверка на TikTok ссылку
    if 'tiktok.com' not in url.lower():
        await update.message.reply_text(
            '❌ Пожалуйста, отправь корректную ссылку на TikTok видео.\n\n'
            'Используй /help для получения помощи.'
        )
        return

    # Проверка, скачивал ли пользователь это видео ранее
    if await database.check_url_exists(url, user.id):
        await update.message.reply_text('ℹ️ Ты уже скачивал это видео ранее!')

    # Отправляем сообщение о начале загрузки
    status_message = await update.message.reply_text('⏳ Начинаю скачивание...')

    try:
        # Скачивание видео
        result = await downloader.download_video(url)

        if not result['success']:
            await status_message.edit_text(f"❌ {result['error']}")
            return

        # Обновляем статус
        await status_message.edit_text('📤 Отправляю видео...')

        # Отправка видео пользователю
        with open(result['file_path'], 'rb') as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=f"🎵 {result['title']}\n👤 {result['uploader']}",
                supports_streaming=True
            )

        # Удаляем статусное сообщение
        await status_message.delete()

        # Сохранение в БД после успешной отправки
        video_id = await database.add_video(
            url=url,
            user_id=user.id,
            username=user.username
        )

        # Очистка файла
        downloader.cleanup_file(result['file_path'])

        logging.info(f"Видео {video_id} успешно отправлено пользователю {user.id}")

    except Exception as e:
        logging.error(f"Ошибка при обработке видео: {e}")
        await status_message.edit_text(
            '❌ Произошла ошибка при обработке видео.\n'
            'Попробуйте еще раз позже.'
        )
        # Очистка файла в случае ошибки
        if 'file_path' in result:
            downloader.cleanup_file(result['file_path'])


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать историю скачиваний пользователя"""
    user = update.effective_user
    videos = await database.get_user_videos(user.id)

    if not videos:
        await update.message.reply_text('📭 У тебя пока нет истории скачиваний.')
        return

    message = '📋 Твоя история скачиваний:\n\n'
    for i, video in enumerate(videos[:10], 1):  # Показываем последние 10
        message += f"{i}. ID: {video['video_id']}\n"
        message += f"   📅 {video['created_at']}\n"
        message += f"   🔗 {video['url'][:50]}...\n\n"

    if len(videos) > 10:
        message += f'...и еще {len(videos) - 10} видео'

    await update.message.reply_text(message)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику"""
    user = update.effective_user
    user_videos = await database.get_user_videos(user.id)
    total_videos = await database.get_total_videos()

    message = (
        f'📊 Статистика:\n\n'
        f'🎥 Твоих видео: {len(user_videos)}\n'
        f'🌍 Всего видео в боте: {total_videos}\n'
        f'👤 Твой ID: {user.id}'
    )

    await update.message.reply_text(message)


async def post_init(application: Application):
    """Инициализация БД при запуске бота"""
    await database.init_db()
    logging.info("База данных инициализирована")


def main():
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Бот запущен!")
    application.run_polling()


if __name__ == '__main__':
    main()