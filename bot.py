import os
import logging
import uuid
from telegram import Update, InlineQueryResultVideo, InlineQueryResultCachedVideo, InputTextMessageContent, \
    InlineQueryResultArticle
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, InlineQueryHandler
from telegram.request import HTTPXRequest
from dotenv import load_dotenv
import database
from downloader import TikTokDownloader

# Загрузка переменных окружения сися
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


async def post_init(application: Application):
    """Инициализация БД при запуске бота"""
    await database.init_db()
    logging.info("База данных инициализирована")


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
                    supports_streaming=True,
                    read_timeout=60,
                    write_timeout=60
                )

                # Добавляем запись для этого пользователя
                await database.update_video_file_id(url, video_data.get('file_id'))
                logging.info(f"Видео отправлено из кэша (file_id) пользователю {user.id}")
                return
            except Exception as e:
                logging.warning(f"Не удалось отправить через file_id: {e}")

        # Если есть файл на диске
        if video_data.get('file_path') and downloader.file_exists(video_data['file_path']):
            status_message = await update.message.reply_text('📤 Отправляю видео из кэша...')

            with open(video_data['file_path'], 'rb') as video_file:
                sent_message = await update.message.reply_video(
                    video=video_file,
                    caption=f"🎵 {video_data.get('title', 'TikTok Video')}",
                    supports_streaming=True,
                    read_timeout=60,
                    write_timeout=60
                )

            if sent_message.video:
                await database.update_video_file_id(url, sent_message.video.file_id)

            await status_message.delete()
            await database.add_user_download(url, user.id, user.username)
            logging.info(f"Видео отправлено из файла пользователю {user.id}")
            return

        # Если файл не найден, скачиваем заново
        status_message = await update.message.reply_text('⚠️ Файл не найден в кэше. Скачиваю заново...')
        await handle_new_video(update, user, url)

    except Exception as e:
        logging.error(f"Ошибка при отправке существующего видео: {e}")
        await handle_new_video(update, user, url)


async def handle_new_video(update: Update, user, url: str):
    """Обработка нового видео - скачивание"""
    status_message = await update.message.reply_text('⏳ Начинаю скачивание...')
    try:
        # Скачивание видео
        result = await downloader.download_video(url)

        if not result['success']:
            await status_message.edit_text(f"❌ {result.get('error', 'Ошибка скачивания')}")
            return

        # Обновляем статус
        await status_message.edit_text('📤 Отправляю видео...')

        # Отправка видео пользователю с увеличенными таймаутами
        with open(result['file_path'], 'rb') as video_file:
            sent_message = await update.message.reply_video(
                video=video_file,
                caption=f"🎵 {result['title']}",
                supports_streaming=True,
                read_timeout=60,  # Таймаут чтения: 60 секунд
                write_timeout=60  # Таймаут записи: 60 секунд
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


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline запросов для работы в диалогах"""
    query = update.inline_query.query.strip()
    user = update.inline_query.from_user

    if not query:
        results = [
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="📝 Вставьте ссылку на видео",
                input_message_content=InputTextMessageContent(
                    message_text="Для использования введите ссылку на TikTok видео"
                )
            )
        ]
        await update.inline_query.answer(results, cache_time=300)
        return

    if 'tiktok.com' not in query.lower():
        results = [
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="❌ Неверная ссылка",
                input_message_content=InputTextMessageContent(
                    message_text="❌ Пожалуйста, отправьте ссылку на TikTok видео"
                )
            )
        ]
        await update.inline_query.answer(results, cache_time=10)
        return

    existing_video = await database.get_video_by_url(query)
    results = []

    if existing_video and existing_video.get('file_id'):
        results.append(
            InlineQueryResultCachedVideo(
                id=str(uuid.uuid4()),
                video_file_id=existing_video['file_id'],
                title=f"🎵 {existing_video.get('title', 'TikTok Video')[:50]}",
                description="♻️ Из кэша"
            )
        )
    else:
        results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title="⏳ Видео не в кэше",
                description="Отправьте ссылку боту в личку для скачивания",
                input_message_content=InputTextMessageContent(
                    message_text=f"📥 Сначала отправьте ссылку боту в личку для скачивания:\n\n{query}"
                )
            )
        )

    await update.inline_query.answer(results, cache_time=300)


def main():
    # Создаем request с увеличенными таймаутами
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

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("raupov", raupov))
    application.add_handler(InlineQueryHandler(inline_query))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Бот запущен!")
    application.run_polling()


if __name__ == '__main__':
    main()