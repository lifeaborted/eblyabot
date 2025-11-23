import os
import logging
import json
from aiohttp import web
from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, \
    InlineKeyboardMarkup, InlineQueryResultVideo, InlineQueryResultCachedVideo, InputTextMessageContent, \
    InlineQueryResultArticle, MenuButtonWebApp, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, InlineQueryHandler, ChosenInlineResultHandler

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

SERVER_URL = os.getenv('SERVER_URL')

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
        logging.info(data)
        url = data.get('url')
        user_id = data.get('user_id')
        username = data.get('username')

        if not user_id:
            user_id = 000

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
                'video_url': existing_video['file_path'],
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
            'video_url': result['file_path'],
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

    # Serve static files
    app.add_routes([web.static('/static', 'webapp/static')])

    # Add other routes
    app.router.add_get('/', serve_webapp)
    app.router.add_get('/videos/{filename}', serve_video)
    app.router.add_post('/api/download', api_download)
    app.router.add_post('/api/send', api_send)

    runner = web.AppRunner(app)
    await runner.setup()
    
    # Use PORT from environment or default to 8080
    port = int(os.environ.get('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Веб-сервер запущен на порту {port}")


async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик данных из Web App"""
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        user = update.effective_user
        logging.info(data)

        if data.get('action') == 'send_video':
            url = data.get('url')  # Добавим URL для обновления БД
            file_id = data.get('file_id')
            video_url = data.get('video_url')
            title = data.get('title', 'TikTok Video')

            sent_message = None

            if file_id:
                # Отправляем через file_id (быстрее)
                sent_message = await update.message.reply_video(
                    video=file_id,
                    caption=f"🎵 {title}",
                    supports_streaming=True,
                    read_timeout=60,
                    write_timeout=60
                )
            elif video_url:
                # Отправляем по URL
                sent_message = await update.message.reply_video(
                    video=video_url,
                    caption=f"🎵 {title}",
                    supports_streaming=True,
                    read_timeout=60,
                    write_timeout=60
                )

            # ВАЖНО: Сохраняем file_id в БД после отправки
            if sent_message and sent_message.video and url:
                new_file_id = sent_message.video.file_id
                await database.update_video_file_id(url, new_file_id)
                logging.info(f"File_id сохранен для URL: {url}")

    except Exception as e:
        logging.error(f"Error handling web app data: {e}")
        await update.message.reply_text("❌ Произошла ошибка при отправке видео")

    except Exception as e:
        logging.error(f"Error handling web app data: {e}")
        await update.message.reply_text("❌ Произошла ошибка при отправке видео")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    text = update.message.text.strip()
    user = update.effective_user

    # Обработка TikTok ссылок
    if 'tiktok.com' not in text.lower():
        await update.message.reply_text(
            '🎵 Ты еблан?\n\n',
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        return

    existing_video = await database.get_video_by_url(text)

    if existing_video:
        await handle_existing_video(update, user, text, existing_video)
    else:
        await handle_new_video(update, user, text)


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

        if video_data.get('file_path'):
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
            logging.info(f"Видео отправлено из файла пользователю {user.id}")
            return

        await update.message.reply_text('⚠️ Файл не найден в кэше. Скачиваю заново...')
        await handle_new_video(update, user, url)

    except Exception as e:
        logging.error(f"Ошибка при отправке существующего видео: {e}")
        await handle_new_video(update, user, url)


# ============ BOT HANDLERS ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user

    # URL с debug режимом
    normal_url = f"{SERVER_URL}/?user_id={user.id}&username={user.username or 'unknown'}"


    try:
        await context.bot.set_chat_menu_button(
            chat_id=user.id,
            menu_button=MenuButtonWebApp(
                text="насрать",
                web_app=WebAppInfo(url=normal_url)
            )
        )

        await update.message.reply_text(
            f'Привет, {user.first_name}! 👋\n\n'
            '🎵 Способы использования:\n\n'
            '1️⃣ Нажми на кнопку для скачивания с сайта\n'
            '2️⃣ Отправь мне ссылку прямо в чат',
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception as e:
        logging.error(f"Error setting menu button: {e}")




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

    await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())


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

    await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())


async def raupov(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /raupov"""
    await update.message.reply_text('Раупов согласны', reply_markup=ReplyKeyboardRemove())


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        '/start - начать работу\n'
        '/history - твоя история скачиваний\n'
        '/stats - статистика\n'
        '/help - помощь',
        reply_markup=ReplyKeyboardRemove())


async def post_init(application: Application):
    """Инициализация БД и веб-сервера при запуске бота"""
    global bot_app
    bot_app = application

    await database.init_db()
    logging.info("База данных инициализирована")

    import asyncio
    asyncio.create_task(start_web_server())


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline запросов"""
    query = update.inline_query.query.strip()

    results = []

    # Если пустой запрос - показываем последние скачанные видео
    if not query:
        all_videos = await database.get_all_videos()

        for video in all_videos:
            if video.get('file_id'):
                # Кодируем URL в ID, чтобы можно было восстановить при выборе
                result_id = f"cached_{video['video_id']}_{uuid.uuid4()}"  # или просто использовать video['url']
                results.append(
                    InlineQueryResultCachedVideo(
                        id=result_id,  # используем специальный ID
                        video_file_id=video['file_id'],
                        title=f"{video.get('title', 'TikTok Video')}",
                        description=f"{video['created_at']} by {video['username']}"
                    )
                )
    # Если введена ссылка
    elif 'tiktok.com' in query.lower():
        existing_video = await database.get_video_by_url(query)

        if existing_video and existing_video.get('file_id'):
            results.append(
                InlineQueryResultCachedVideo(
                    id=str(uuid.uuid4()),
                    video_file_id=existing_video['file_id'],
                    title=f"🎵 {existing_video.get('title', 'TikTok Video')[:50]}",
                    description="♻️ Из кэша"
                )
            )
            #await database.update_video_file_id(existing_video['url'], existing_video['file_id'])
        else:
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="⏳ Видео не скачано",
                    description="Скачать...",
                    input_message_content=InputTextMessageContent(
                        message_text=query
                    )
                )
            )

    await update.inline_query.answer(results, cache_time=5, is_personal=True)


async def chosen_inline_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result_id = update.chosen_inline_result.result_id
    query = update.chosen_inline_result.query
    user = update.chosen_inline_result.from_user

    # Если был запрос с URL, обрабатываем как раньше
    if 'tiktok.com' in query.lower():
        existing_video = await database.get_video_by_url(query)
        if existing_video and existing_video.get('file_id'):
            await database.update_video_file_id(existing_video['url'], existing_video['file_id'])
            logging.info(
                f"Выбрано кэшированное видео (по URL) из инлайн запроса для URL: {query}, пользователь: {user.id}")
    # Если был пустой запрос и пользователь выбрал одно из видео
    elif result_id.startswith('cached_'):
        # Извлекаем video_id из result_id
        try:
            # Формат: cached_{video_id}_{uuid}
            parts = result_id.split('_')
            if len(parts) >= 2:
                video_id = int(parts[1])
                # Получаем видео по ID из базы
                video = await database.get_video_by_id(video_id)
                if video and video.get('file_id'):
                    await database.update_video_file_id(video['url'], video['file_id'])
                    logging.info(
                        f"Выбрано кэшированное видео (по ID) из инлайн запроса для URL: {video['url']}, пользователь: {user.id}")
        except (ValueError, IndexError):
            logging.error(f"Невозможно извлечь video_id из result_id: {result_id}")


async def api_send(request):
    """API для отправки видео в чат"""
    try:
        data = await request.json()
        logging.info(f"=== API Send Request ===")
        logging.info(f"Request data: {data}")

        user_id = data.get('user_id')
        chat_id = data.get('chat_id') or user_id
        url = data.get('url')
        file_id = data.get('file_id')
        video_url = data.get('video_url')
        title = data.get('title', 'TikTok Video')

        logging.info(f"user_id={user_id}, chat_id={chat_id}")

        if not user_id:
            return web.json_response({
                'success': False,
                'error': 'user_id обязателен'
            })

        # Создаем новый экземпляр Bot
        from telegram import Bot
        bot = Bot(token=BOT_TOKEN)

        sent_message = None

        # Пробуем отправить через file_id
        if file_id:
            try:
                logging.info(f"Attempting send to {chat_id} via file_id: {file_id}")
                sent_message = await bot.send_video(
                    chat_id=chat_id,
                    video=file_id,
                    caption=f"🎵 {title}",
                    read_timeout=60,
                    write_timeout=60
                )
                logging.info("✅ Successfully sent via file_id")
            except Exception as e:
                logging.error(f"❌ Failed to send via file_id: {e}")

        # Если file_id не сработал, пробуем через URL
        if not sent_message and video_url:
            try:
                logging.info(f"Attempting send to {chat_id} via video_url: {video_url}")
                sent_message = await bot.send_video(
                    chat_id=chat_id,
                    video=video_url,
                    caption=f"🎵 {title}",
                    read_timeout=60,
                    write_timeout=60
                )
                logging.info("✅ Successfully sent via video_url")
            except Exception as e:
                logging.error(f"❌ Failed to send via video_url: {e}")

        # Сохраняем file_id
        if sent_message and sent_message.video and url:
            new_file_id = sent_message.video.file_id
            await database.update_video_file_id(url, new_file_id)
            logging.info(f"File_id updated in DB: {new_file_id}")

        logging.info("=== End API Send Request ===")

        if sent_message:
            return web.json_response({
                'success': True,
                'message': 'Видео отправлено'
            })
        else:
            return web.json_response({
                'success': False,
                'error': 'Не удалось отправить видео'
            })

    except Exception as e:
        logging.error(f"❌ API send error: {e}", exc_info=True)
        return web.json_response({
            'success': False,
            'error': str(e)
        })


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
    application.add_handler(CommandHandler("help", help))
    application.add_handler(InlineQueryHandler(inline_query))
    application.add_handler(ChosenInlineResultHandler(chosen_inline_result))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logging.info("Бот запущен!")
    application.run_polling()


if __name__ == '__main__':
    main()