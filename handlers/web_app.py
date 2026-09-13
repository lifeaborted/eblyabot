import json
from aiogram import Router, F, Bot
from aiogram.types import Message
import database
import logging
logger = logging.getLogger(__name__)

router = Router()

@router.message(F.web_app_data)
async def handle_web_app_data(message: Message, bot: Bot):
    try:
        data = json.loads(message.web_app_data.data)
        if data.get('action') == 'send_video':
            url = data.get('url')
            title = data.get('title', 'Видео')
            file_id = data.get('file_id')
            video_url = data.get('video_url')

            if file_id:
                sent = await message.answer_video(video=file_id, caption=title)
            elif video_url:
                from aiogram.types import FSInputFile
                sent = await message.answer_video(video=FSInputFile(video_url), caption=title)

            if sent and sent.video and url:
                await database.update_video_file_id(url, sent.video.file_id)

    except Exception as e:
        logger.error(f"Error handling web app data: {e}")
        await message.answer("Не удалось отправить видео.")