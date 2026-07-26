import json
import logging
from telegram import Update
from telegram.ext import ContextTypes
import database

logger = logging.getLogger(__name__)


async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик данных из Web App"""
    try:
        data = json.loads(update.effective_message.web_app_data.data)
        logger.info(f"Web App Data received: {data}")

        if data.get('action') == 'send_video':
            url = data.get('url')
            file_id = data.get('file_id')
            video_url = data.get('video_url')
            title = data.get('title', 'Media Video')

            sent_message = None

            if file_id:
                sent_message = await update.message.reply_video(
                    video=file_id,
                    caption=f"🎵 {title}",
                    supports_streaming=True,
                    read_timeout=60,
                    write_timeout=60
                )
            elif video_url:
                sent_message = await update.message.reply_video(
                    video=video_url,
                    caption=f"🎵 {title}",
                    supports_streaming=True,
                    read_timeout=60,
                    write_timeout=60
                )

            if sent_message and sent_message.video and url:
                new_file_id = sent_message.video.file_id
                await database.update_video_file_id(url, new_file_id)
                logger.info(f"File_id сохранен для URL: {url}")

    except Exception as e:
        logger.error(f"Error handling web app data: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка при отправке видео")
