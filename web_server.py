import os
import json
import logging
from aiohttp import web
from telegram import Bot
from config import BOT_TOKEN, PORT, DOWNLOAD_DIR
from downloader import MediaDownloader
import database

logger = logging.getLogger(__name__)
downloader = MediaDownloader()


async def serve_webapp(request):
    """Отдача Web App интерфейса"""
    file_path = os.path.join('webapp', 'index.html')
    if not os.path.exists(file_path):
        return web.Response(status=404, text="Index file not found in webapp/")
    return web.FileResponse(file_path)


async def serve_video(request):
    """Отдача медиа файлов"""
    filename = request.match_info['filename']
    file_path = os.path.join(DOWNLOAD_DIR, filename)

    if not os.path.exists(file_path):
        return web.Response(status=404, text="File not found")

    return web.FileResponse(file_path)


async def api_download(request):
    """API для скачивания медиа"""
    try:
        data = await request.json()
        logger.info(f"API Download Request: {data}")
        url = data.get('url')
        user_id = data.get('user_id', 0)
        username = data.get('username')

        if not url or not downloader.is_supported_url(url):
            return web.json_response({
                'success': False,
                'error': 'Неверная ссылка. Поддерживаются TikTok и YouTube.'
            })

        # Проверяем кэш
        existing_video = await database.get_video_by_url(url)

        # === ИСПРАВЛЕННЫЙ БЛОК КЭША ===
        if existing_video:
            file_path = existing_video.get('file_path')

            # Проверяем, существует ли файл физически на диске
            if file_path and os.path.exists(file_path):
                filename = os.path.basename(file_path)
                return web.json_response({
                    'success': True,
                    'title': existing_video.get('title', 'Media Item'),
                    'uploader': existing_video.get('uploader', 'Unknown'),
                    'file_id': existing_video.get('file_id'),
                    'video_url': f"/videos/{filename}",  # Отдаем фронтенду правильный веб-роут
                    'media_type': existing_video.get('media_type', 'video'),
                    'from_cache': True
                })
            # Если файла нет на диске (удален ботом), игнорируем кэш и качаем заново

        # Скачиваем новое медиа
        result = await downloader.download_media(url)

        if not result['success']:
            return web.json_response({
                'success': False,
                'error': result.get('error', 'Ошибка скачивания')
            })

        media_type = result.get('media_type', 'video')
        file_path = result.get('file_path') if media_type == 'video' else (result.get('image_paths', [None])[0])

        # Получаем только имя файла для формирования ссылки
        filename = os.path.basename(file_path) if file_path else None

        video_id = await database.add_video(
            url=url,
            user_id=user_id,
            username=username,
            file_path=file_path,
            file_id=existing_video.get('file_id') if existing_video else None,  # Если был старый file_id, сохраняем его
            title=result['title'],
            media_type=media_type
        )

        return web.json_response({
            'success': True,
            'title': result['title'],
            'uploader': result.get('uploader', 'Unknown'),
            'video_url': f"/videos/{filename}" if filename else file_path,  # Отдаем фронтенду правильный веб-роут
            'video_id': video_id,
            'media_type': media_type,
            'from_cache': False
        })

    except Exception as e:
        logger.error(f"API Download Error: {e}", exc_info=True)
        return web.json_response({
            'success': False,
            'error': str(e)
        })


async def api_send(request):
    """API для отправки медиа в чат"""
    try:
        data = await request.json()
        logger.info(f"API Send Request: {data}")

        user_id = data.get('user_id')
        chat_id = data.get('chat_id') or user_id
        url = data.get('url')
        file_id = data.get('file_id')
        video_url = data.get('video_url')
        title = data.get('title', 'Media Item')

        if not user_id:
            return web.json_response({
                'success': False,
                'error': 'user_id обязателен'
            })

        sent_message = None

        # Оборачиваем Bot в асинхронный контекстный менеджер для корректного закрытия HTTP сессии
        async with Bot(token=BOT_TOKEN) as bot:
            if file_id:
                try:
                    sent_message = await bot.send_video(
                        chat_id=chat_id,
                        video=file_id,
                        caption=f"🎵 {title}",
                        read_timeout=60,
                        write_timeout=60
                    )
                except Exception as e:
                    logger.error(f"Failed to send via file_id: {e}")

            if not sent_message and video_url and os.path.exists(video_url):
                try:
                    with open(video_url, 'rb') as f:
                        sent_message = await bot.send_video(
                            chat_id=chat_id,
                            video=f,
                            caption=f"🎵 {title}",
                            read_timeout=60,
                            write_timeout=60
                        )
                except Exception as e:
                    logger.error(f"Failed to send via local file: {e}")

        # Обновляем БД вне контекстного менеджера, так как нам нужна только информация из sent_message
        if sent_message and sent_message.video and url:
            new_file_id = sent_message.video.file_id
            await database.update_video_file_id(url, new_file_id)

        if sent_message:
            return web.json_response({
                'success': True,
                'message': 'Медиа успешно отправлено'
            })
        else:
            return web.json_response({
                'success': False,
                'error': 'Не удалось отправить медиа'
            })

    except Exception as e:
        logger.error(f"API Send Error: {e}", exc_info=True)
        return web.json_response({
            'success': False,
            'error': str(e)
        })


async def start_web_server():
    """Запуск веб-сервера aiohttp"""
    app = web.Application()

    app.add_routes([web.static('/static', os.path.join('webapp', 'static'))])
    app.router.add_get('/', serve_webapp)
    app.router.add_get('/videos/{filename}', serve_video)
    app.router.add_post('/api/download', api_download)
    app.router.add_post('/api/send', api_send)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, '0.0.0.0', PORT, reuse_address=True)
    await site.start()

    logger.info(f"Веб-сервер запущен на порту {PORT}")