import uuid
import logging
from telegram import Update, InlineQueryResultCachedVideo, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes
import database

logger = logging.getLogger(__name__)


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline запросов"""
    query = update.inline_query.query.strip()
    results = []

    if not query:
        all_videos = await database.get_all_videos()

        for video in all_videos:
            if video.get('file_id') and video.get('media_type') != 'images':
                result_id = f"cached_{video['video_id']}_{uuid.uuid4()}"
                results.append(
                    InlineQueryResultCachedVideo(
                        id=result_id,
                        video_file_id=video['file_id'],
                        title=f"{video.get('title', 'Media Video')}",
                        description=f"{video['created_at']} by {video['username']}"
                    )
                )
    elif 'tiktok.com' in query.lower() or 'youtube.com' in query.lower() or 'youtu.be' in query.lower():
        existing_video = await database.get_video_by_url(query)

        if existing_video and existing_video.get('file_id') and existing_video.get('media_type') != 'images':
            results.append(
                InlineQueryResultCachedVideo(
                    id=str(uuid.uuid4()),
                    video_file_id=existing_video['file_id'],
                    title=f"🎵 {existing_video.get('title', 'Media Video')[:50]}",
                    description="♻️ Из кэша"
                )
            )
        else:
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="⏳ Медиа не скачано",
                    description="Скачать...",
                    input_message_content=InputTextMessageContent(
                        message_text=query
                    )
                )
            )

    await update.inline_query.answer(results, cache_time=5, is_personal=True)


async def chosen_inline_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбранного результата из inline запроса"""
    result_id = update.chosen_inline_result.result_id
    query = update.chosen_inline_result.query
    user = update.chosen_inline_result.from_user

    if 'tiktok.com' in query.lower() or 'youtube.com' in query.lower() or 'youtu.be' in query.lower():
        existing_video = await database.get_video_by_url(query)
        if existing_video and existing_video.get('file_id'):
            await database.update_video_file_id(existing_video['url'], existing_video['file_id'])
            logger.info(f"Выбрано кэшированное видео из инлайн запроса по URL: {query}, user: {user.id}")
    elif result_id.startswith('cached_'):
        try:
            parts = result_id.split('_')
            if len(parts) >= 2:
                video_id = int(parts[1])
                video = await database.get_video_by_id(video_id)
                if video and video.get('file_id'):
                    await database.update_video_file_id(video['url'], video['file_id'])
                    logger.info(f"Выбрано кэшированное видео из инлайн запроса по ID: {video['url']}, user: {user.id}")
        except (ValueError, IndexError):
            logger.error(f"Невозможно извлечь video_id из result_id: {result_id}")
