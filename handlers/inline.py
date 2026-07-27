import uuid
import json
import logging
from telegram import (
    Update,
    InlineQueryResultCachedVideo,
    InlineQueryResultCachedPhoto,
    InlineQueryResultsButton
)
from telegram.ext import ContextTypes
import database

logger = logging.getLogger(__name__)


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline запросов"""
    query = update.inline_query.query.strip()
    results = []

    if not query:
        # Показываем последние скачанные видео из базы
        all_videos = await database.get_all_videos()

        for video in all_videos[:25]:
            if not video.get('file_id'):
                continue

            result_id = f"cached_{video['video_id']}_{uuid.uuid4()}"

            if video.get('media_type') == 'images':
                try:
                    file_ids = json.loads(video['file_id'])
                    if file_ids and isinstance(file_ids, list):
                        results.append(
                            InlineQueryResultCachedPhoto(
                                id=result_id,
                                photo_file_id=file_ids[0],
                                title=f"📸 {video.get('title', 'Фото')[:50]}",
                                description="Слайдшоу из кэша"
                            )
                        )
                except json.JSONDecodeError:
                    pass
            else:
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

        # Проверяем кэш
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

        # Если это ссылка, но ее НЕТ в кэше
        button_config = None
        if (
                'tiktok.com' in query.lower() or 'youtube.com' in query.lower() or 'youtu.be' in query.lower()) and not results:

            chat_type = update.inline_query.chat_type

            if chat_type == 'private':
                # 1. Мы в ЛС с другим человеком: тут бот физически не может читать сообщения.
                # Показываем ТОЛЬКО кнопку редиректа в бота.
                button_config = InlineQueryResultsButton(
                    text="📥 Скачать новое видео в ЛС бота",
                    start_parameter="new_download"
                )
            else:
                # 2. Мы в группе, супергруппе или в ЛС с самим ботом.
                # Разрешаем выкинуть ссылку текстом, чтобы бот ее поймал.
                results.append(
                    InlineQueryResultArticle(
                        id=str(uuid.uuid4()),
                        title="⏳ Скачать прямо в этот чат",
                        description="Бот скачает видео сюда (если он есть в чате)",
                        input_message_content=InputTextMessageContent(
                            message_text=query
                        )
                    )
                )
                # Оставляем кнопку редиректа на всякий случай
                # (вдруг пользователь вызывает инлайн в группе, где бота еще нет)
                button_config = InlineQueryResultsButton(
                    text="📥 Или скачать через ЛС бота",
                    start_parameter="new_download"
                )

        await update.inline_query.answer(
            results,
            cache_time=5,
            is_personal=True,
            button=button_config
        )


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