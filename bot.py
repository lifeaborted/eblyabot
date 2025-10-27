import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import database
from downloader import TikTokDownloader

<<<<<<< HEAD
# Загрузка переменных окружения сися
=======
# Загрузка переменных окружения
>>>>>>> c4e063a (я докер поднял)
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Проверка токена
BOT_TOKEN = os.getenv('BOT_TOKEN')
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
        'Для помощи отправь команду /help'
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
        '• https://vm.tiktok.com/...\n\n'
        '📋 Доступные команды:\n'
        '/start - начать работу\n'
        '/history - твоя история скачиваний\n'
        '/stats - статистика\n'
        '/help - помощь\n'
        '/raupov - raupov'
    )

async def raupov(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    await update.message.reply_text(
        f'Раупов согласны'
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    url = update.message.text.strip()
    user = update.effective_user

    # Проверка на TikTok ссылку
    if 'tiktok.com' not in url.lower():
        await update.message.reply_text(
            'Тупорылое уебище тебе русским языком написали: ТОЛЬКО БЛЯДЬ ССЫЛКИ НА ТИКТОК ВИДОСЫ, хули ты срешь сюда пидорас')
        return

    # Проверяем, есть ли видео в базе
    existing_video = await database.get_video_by_url(url)

    if existing_video:
        await handle_existing_video(update, user, url, existing_video)
    else:
        await handle_new_video(update, user, url)


async def handle_existing_video(update: Update, user, url: str, video_data: dict):
    """Обработка существующего видео из БД"""
    try:
        # Пытаемся отправить через file_id (самый быстрый способ)
        if video_data.get('file_id'):
            try:
                await update.message.reply_video(
                    video=video_data['file_id'],
                    caption=f"🎵 {video_data.get('title', 'TikTok Video')}",
                    supports_streaming=True
                )

                # Добавляем запись для этого пользователя
                await database.update_video_file_id(url, video_data.get('file_id'))
                logging.info(f"Видео отправлено из кэша (file_id) пользователю {user.id}")
                return
            except Exception as e:
                logging.warning(f"Не удалось отправить через file_id: {e}")

        # Если файл не найден, скачиваем заново
        else:
            await status_message.edit_text('⚠️ Файл не найден в кэше. Скачиваю заново...')
            await handle_new_video(update, user, url)
            logging.info(f"Видео {url} скачано заново пользователю {user.id}")

    except Exception as e:
        logging.error(f"Ошибка при отправке существующего видео: {e}")
        await status_message.edit_text('❌ Ошибка при отправке. Попробую скачать заново...')
        await handle_new_video(update, user, url)


async def handle_new_video(update: Update, user, url: str):
    """Обработка нового видео - скачивание"""
    status_message = await update.message.reply_text('⏳ Начинаю скачивание...')
    try:
        # Скачивание видео
        result = await downloader.download_video(url)

        if not result['success']:
            return

        # Обновляем статус
        await status_message.edit_text('📤 Отправляю видео...')


        # Отправка видео пользователю
        with open(result['file_path'], 'rb') as video_file:
            sent_message = await update.message.reply_video(
                video=video_file,
                caption=f"🎵 {result['title']}",
                supports_streaming=True
            )
        # Удаляем статусное сообщение
        await status_message.delete()

        # Сохраняем в БД с file_id
        file_id = sent_message.video.file_id if sent_message.video else None

        video_id = await database.add_video(
            url=url,
            user_id=user.id,
            username=user.username,
            file_path=result['file_path'],
            file_id=file_id,
            title=result['title']
        )
        logging.info(f"Новое видео {video_id} успешно скачано и отправлено пользователю {user.id}")

    except Exception as e:
        logging.error(f"Ошибка при обработке видео: {e}")
        await status_message.edit_text(
            '❌ Произошла ошибка при обработке видео.\n'
            'Попробуйте еще раз позже.'
        )


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать историю скачиваний пользователя"""
    user = update.effective_user
    videos = await database.get_user_videos(user.id)

    if not videos:
        await update.message.reply_text('📭 У тебя пока нет истории скачиваний.')
        return

    message = '📋 Твоя история скачиваний:\n\n'
    for i, video in enumerate(videos[:10], 1):  # Показываем последние 10
        title = video.get('title', 'TikTok Video')
        message += f"{i}. {title[:30]}...\n"
        message += f"   📅 {video['created_at']}\n"
        message += f"   🔗 {video['url'][:40]}...\n\n"

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
        f'🎥 Твоих скачиваний: {len(user_videos)}\n'
        f'🌍 Всего скачиваний в боте: {total_videos}\n'
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
    application.add_handler(CommandHandler("raupov", raupov))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Бот запущен!")
    application.run_polling()


if __name__ == '__main__':
<<<<<<< HEAD
    main()
=======
    main()
>>>>>>> c4e063a (я докер поднял)
