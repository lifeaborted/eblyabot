import os
import logging
from aiohttp import web
from aiogram import Bot
from aiogram.types import FSInputFile
from config import BOT_TOKEN, PORT, DOWNLOAD_DIR
from downloaders.factory import DownloaderFactory
import database

logger = logging.getLogger(__name__)


async def serve_webapp(request):
    return web.FileResponse(os.path.join('webapp', 'index.html'))


async def serve_video(request):
    file_path = os.path.join(DOWNLOAD_DIR, request.match_info['filename'])
    if not os.path.exists(file_path): return web.Response(status=404)
    return web.FileResponse(file_path)


async def api_download(request):
    data = await request.json()
    url = data.get('url')

    existing = await database.get_video_by_url(url)
    if existing and existing.get('file_path') and os.path.exists(existing['file_path']):
        return web.json_response({
            'success': True, 'title': existing.get('title'),
            'file_id': existing.get('file_id'),
            'video_url': f"/videos/{os.path.basename(existing['file_path'])}",
            'media_type': existing.get('media_type')
        })

    downloader = DownloaderFactory.get(url, DOWNLOAD_DIR)
    if not downloader: return web.json_response({'success': False, 'error': 'Unsupported'})

    result = await downloader.download(url)
    if not result['success']: return web.json_response({'success': False, 'error': result['error']})

    media_type = result.get('media_type', 'video')
    file_path = result.get('file_path') if media_type == 'video' else result.get('image_paths', [None])[0]
    filename = os.path.basename(file_path) if file_path else None

    video_id = await database.add_video(
        url=url, user_id=data.get('user_id', 0), username=data.get('username'),
        file_path=file_path, file_id=existing.get('file_id') if existing else None,
        title=result['title'], media_type=media_type
    )

    return web.json_response({
        'success': True, 'title': result['title'],
        'video_url': f"/videos/{filename}" if filename else file_path,
        'video_id': video_id, 'media_type': media_type
    })


async def api_send(request):
    data = await request.json()
    chat_id = data.get('chat_id') or data.get('user_id')

    # aiogram 3 позволяет использовать Bot как асинхронный контекстный менеджер для закрытия сессии HTTP
    async with Bot(token=BOT_TOKEN) as bot:
        sent = None
        if data.get('file_id'):
            sent = await bot.send_video(chat_id=chat_id, video=data['file_id'], caption=f"🎵 {data.get('title')}")
        elif data.get('video_url') and os.path.exists(data['video_url']):
            sent = await bot.send_video(chat_id=chat_id, video=FSInputFile(data['video_url']),
                                        caption=f"🎵 {data.get('title')}")

        if sent and sent.video:
            await database.update_video_file_id(data['url'], sent.video.file_id)
            return web.json_response({'success': True})

    return web.json_response({'success': False, 'error': 'Failed'})


async def start_web_server():
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
    logger.info(f"Веб-сервер aiohttp запущен на порту {PORT}")