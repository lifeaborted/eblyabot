import uuid
import json
import logging
from telegram import (
    Update,
    InlineQueryResultCachedVideo,
    InlineQueryResultCachedPhoto,
    InlineQueryResultArticle,
    InputTextMessageContent
)
from telegram.ext import ContextTypes
import database

logger = logging.getLogger(__name__)


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline запросов"""
    query = update.inline_query.query.strip()
    results = []

    if not query:
        # Если запрос пустой, показываем историю скачиваний из базы
        all_videos = await database.get_all_videos()

        for video in all_videos[:25]:  # Ограничиваем выдачу для скорости
            if not video.get('file_id'):
                continue

            result_id = f"cached_{video['video_id']}_{uuid.uuid4()}"

            # Поддержка фото-каруселей TikTok
            if video.get('media_type') == 'images':
                try:
                    file_ids = json.loads(video['file_id'])
                    if file_ids and isinstance(file_ids, list):
                        results.append(
                            InlineQueryResultCachedPhoto(
                                id=result_id,
                                photo_file_id=file_ids[0],  # Превью: первое фото из слайдшоу
                                title=f"📸 {video.get('title', 'Фото')[:50]}",
                                description="Слайдшоу из кэша"
                            )
                        )
                except json.JSONDecodeError:
                    pass
            else:
                # Поддержка обычных видео
                results.append(
                    InlineQueryResultCachedVideo(
                        id=result_id,
                        video_file_id=video['file_id'],
                        title=f"🎵 {video.get('title', 'Media Video')}",
                        description=f"{video['created_at']} by {video['username']}"
                    )
                )
    elif 'tiktok.com' in query.lower() or 'youtube.com' in query.lower() or 'youtu.be' in query.lower():
        existing_video = await database.get_video_by_url(query)

        # Проверяем, есть ли кэш И существует ли сохраненный file_id в Telegram
        if existing_video and existing_video.get('file_id'):
            if existing_video.get('media_type') == 'images':
                try:
                    file_ids = json.loads(existing_video['file_id'])
                    if file_ids and isinstance(file_ids, list):
                        results.append(
                            InlineQueryResultCachedPhoto(
                                id=str(uuid.uuid4()),
                                photo_file_id=file_ids[0],
                                title=f"📸 {existing_video.get('title', 'Фото')[:50]}",
                                description="♻️ Из кэша"
                            )
                        )
                except json.JSONDecodeError:
                    pass
            else:
                results.append(
                    InlineQueryResultCachedVideo(
                        id=str(uuid.uuid4()),
                        video_file_id=existing_video['file_id'],
                        title=f"🎵 {existing_video.get('title', 'Media Video')[:50]}",
                        description="♻️ Из кэша"
                    )
                )

        # Если результатов нет (файла нет в кэше или нет file_id), выводим кнопку для старта скачивания
        if not results:
            results.append(
                InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="⏳ Скачать медиа",
                    description="Нажми сюда, чтобы бот скачал это видео прямо в чат",
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