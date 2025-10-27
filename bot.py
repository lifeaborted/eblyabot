import os
import logging
import json
from aiohttp import web
from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, \
InlineQueryResultVideo, InlineQueryResultCachedVideo, InputTextMessageContent, InlineQueryResultArticle
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, InlineQueryHandler
from dotenv import load_dotenv
import uuid
from telegram.request import HTTPXRequest
import database
from downloader import TikTokDownloader

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден! Проверьте файл .env")

SERVER_URL = os.getenv('SERVER_URL', 'http://localhost:8080')

downloader = TikTokDownloader()
bot_app = None  # Глобальная переменная для доступа к Application


# ============ WEB SERVER ============
async def serve_webapp(request):
    """Отдача Web App интерфейса"""
    with open('webapp/index.html', 'r', encoding='utf-8') as f:
        html = f.read()
    return web.Response(text=html, content_type='text/html')


async def serve_video(request):
    """Отдача видео файлов"""
    filename = request.match_info['filename']
    file_path = os.path.join('downloads_main', filename)

    if not os.path.exists(file_path):
        return web.Response(status=404, text="File not found")

    return web.FileResponse(file_path)


async def api_download(request):
    """API для скачивания видео"""
    try:
        data = await request.json()
        url = data.get('url')
        user_id = data.get('user_id')
        username = data.get('username')

        if not url or 'tiktok.com' not in url.lower():
            return web.json_response({
                'success': False,
                'error': 'Неверная ссылка на TikTok'
            })

        # Проверяем кэш
        existing_video = await database.get_video_by_url(url)

        if existing_video and existing_video.get('file_id'):
            filename = os.path.basename(existing_video['file_path'])
            return web.json_response({
                'success': True,
                'title': existing_video.get('title', 'TikTok Video'),
                'uploader': existing_video.get('uploader', 'Unknown'),
                'file_id': existing_video['file_id'],
                'video_url': f"{SERVER_URL}/videos/{filename}",
                'from_cache': True
            })

        # Скачиваем новое видео
        result = await downloader.download_video(url)

        if not result['success']:
            return web.json_response({
                'success': False,
                'error': result.get('error', 'Ошибка скачивания')
            })

        # Сохраняем в БД
        video_id = await database.add_video(
            url=url,
            user_id=user_id,
            username=username,
            file_path=result['file_path'],
            file_id=None,
            title=result['title']
        )

        filename = os.path.basename(result['file_path'])

        return web.json_response({
            'success': True,
            'title': result['title'],
            'uploader': result.get('uploader', 'Unknown'),
            'video_url': f"{SERVER_URL}/videos/{filename}",
            'video_id': video_id,
            'from_cache': False
        })

    except Exception as e:
        logging.error(f"API Error: {e}")
        return web.json_response({
            'success': False,
            'error': str(e)
        })


async def start_web_server():
    """Запуск веб-сервера"""
    app = web.Application()
    app.router.add_get('/', serve_webapp)
    app.router.add_get('/videos/{filename}', serve_video)
    app.router.add_post('/api/download', api_download)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logging.info("Веб-сервер запущен на порту 8080")


# ============ BOT HANDLERS ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user

    # Создаем кнопку для открытия Web App
    keyboard = [
        [KeyboardButton(
            text="🎵 Открыть TikTok Downloader",
            web_app=WebAppInfo(url=f"{SERVER_URL}/")
        )]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        f'Привет, {user.first_name}! 👋\n\n'
        '🎵 Нажми на кнопку ниже, чтобы открыть приложение для скачивания TikTok видео!\n\n'
        'Или отправь мне ссылку прямо сюда.',
        reply_markup=reply_markup
    )


async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик данных из Web App"""
    try:
        data = json.loads(update.effective_message.web_app_data.data)

        if data.get('action') == 'send_video':
            file_id = data.get('file_id')
            video_url = data.get('video_url')
            title = data.get('title', 'TikTok Video')

            if file_id:
                # Отправляем через file_id (быстрее)
                await update.message.reply_video(
                    video=file_id,
                    caption=f"🎵 {title}",
                    supports_streaming=True
                )
            elif video_url:
                # Отправляем по URL
                await update.message.reply_video(
                    video=video_url,
                    caption=f"🎵 {title}",
                    supports_streaming=True
                )

    except Exception as e:
        logging.error(f"Error handling web app data: {e}")
        await update.message.reply_text("❌ Произошла ошибка при отправке видео")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    url = update.message.text.strip()
    user = update.effective_user

    if 'tiktok.com' not in url.lower():
        await update.message.reply_text(
            'Тупорылое уебище тебе русским языком написали: ТОЛЬКО БЛЯДЬ ССЫЛКИ НА ТИКТОК ВИДОСЫ, хули ты срешь сюда пидорас')
        return

    existing_video = await database.get_video_by_url(url)

    if existing_video:
        await handle_existing_video(update, user, url, existing_video)
    else:
        await handle_new_video(update, user, url)


async def handle_existing_video(update: Update, user, url: str, video_data: dict):
    """Обработка существующего видео из БД"""
    try:
        if video_data.get('file_id'):
            try:
                sent_message = await update.message.reply_video(
                    video=video_data['file_id'],
                    caption=f"🎵 {video_data.get('title', 'TikTok Video')}",
                    supports_streaming=True
                )
                await database.update_video_file_id(url, video_data.get('file_id'))
                logging.info(f"Видео отправлено из кэша (file_id) пользователю {user.id}")
                return
            except Exception as e:
                logging.warning(f"Не удалось отправить через file_id: {e}")

        if video_data.get('file_path') and downloader.file_exists(video_data['file_path']):
            status_message = await update.message.reply_text('📤 Отправляю видео из кэша...')

            with open(video_data['file_path'], 'rb') as video_file:
                sent_message = await update.message.reply_video(
                    video=video_file,
                    caption=f"🎵 {video_data.get('title', 'TikTok Video')}",
                    supports_streaming=True
                )

            if sent_message.video:
                await database.update_video_file_id(url, sent_message.video.file_id)

            await status_message.delete()
            await database.add_user_download(url, user.id, user.username)
            logging.info(f"Видео отправлено из файла пользователю {user.id}")
            return

        await update.message.reply_text('⚠️ Файл не найден в кэше. Скачиваю заново...')
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


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать историю скачиваний пользователя"""
    user = update.effective_user
    videos = await database.get_user_videos(user.id)

    if not videos:
        await update.message.reply_text('📭 У тебя пока нет истории скачиваний.')
        return

    message = '📋 Твоя история скачиваний:\n\n'
    for i, video in enumerate(videos[:10], 1):
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


async def raupov(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /raupov"""
    await update.message.reply_text('Раупов согласны')


async def post_init(application: Application):
    """Инициализация БД и веб-сервера при запуске бота"""
    global bot_app
    bot_app = application

    await database.init_db()
    logging.info("База данных инициализирована")

    import asyncio
    asyncio.create_task(start_web_server())


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
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("raupov", raupov))
    application.add_handler(InlineQueryHandler(inline_query))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Бот запущен!")
    application.run_polling()


if __name__ == '__main__':
    main()