import uuid
import json
from aiogram import Router
from aiogram.types import (
    InlineQuery, ChosenInlineResult, InlineQueryResultCachedVideo,
    InlineQueryResultCachedPhoto, InlineQueryResultArticle,
    InputTextMessageContent, InlineQueryResultsButton
)
import database
import logging
logger = logging.getLogger(__name__)

router = Router()

@router.inline_query()
async def inline_query_handler(inline_query: InlineQuery):
    query = inline_query.query.strip()
    results = []
    button_config = None

    if not query:
        all_videos = await database.get_all_videos()
        for video in all_videos[:25]:
            if not video.get('file_id'): continue
            result_id = f"cached_{video['video_id']}_{uuid.uuid4()}"

            if video.get('media_type') == 'images':
                try:
                    file_ids = json.loads(video['file_id'])
                    if file_ids and isinstance(file_ids, list):
                        results.append(InlineQueryResultCachedPhoto(
                            id=result_id, photo_file_id=file_ids[0],
                            title=f"Фото: {video.get('title', 'Изображение')[:50]}", description="Сохранено ранее"
                        ))
                except json.JSONDecodeError:
                    pass
            else:
                results.append(InlineQueryResultCachedVideo(
                    id=result_id, video_file_id=video['file_id'],
                    title=f"Видео: {video.get('title', 'Медиа')}", description="Сохранено ранее"
                ))
    elif any(d in query.lower() for d in ['tiktok.com', 'youtube.com', 'youtu.be']):
        existing_video = await database.get_video_by_url(query)
        if existing_video and existing_video.get('file_id'):
            if existing_video.get('media_type') == 'images':
                try:
                    file_ids = json.loads(existing_video['file_id'])
                    results.append(InlineQueryResultCachedPhoto(
                        id=str(uuid.uuid4()), photo_file_id=file_ids[0],
                        title=f"Фото: {existing_video.get('title', 'Изображение')[:50]}", description="Сохранено ранее"
                    ))
                except json.JSONDecodeError:
                    pass
            else:
                results.append(InlineQueryResultCachedVideo(
                    id=str(uuid.uuid4()), video_file_id=existing_video['file_id'],
                    title=f"Видео: {existing_video.get('title', 'Медиа')[:50]}", description="Сохранено ранее"
                ))

        if not results:
            if inline_query.chat_type == 'sender':
                button_config = InlineQueryResultsButton(text="Скачать новое видео через личные сообщения",
                                                         start_parameter="new_download")
            else:
                results.append(InlineQueryResultArticle(
                    id=str(uuid.uuid4()), title="Скачать видео в этот чат",
                    description="Нажмите для начала загрузки",
                    input_message_content=InputTextMessageContent(message_text=query)
                ))

    await inline_query.answer(results, cache_time=0, is_personal=True, button=button_config)

@router.chosen_inline_result()
async def chosen_inline_result_handler(chosen_result: ChosenInlineResult):
    query = chosen_result.query
    if any(d in query.lower() for d in ['tiktok.com', 'youtube.com', 'youtu.be']):
        video = await database.get_video_by_url(query)
        if video and video.get('file_id'):
            await database.update_video_file_id(video['url'], video['file_id'])
    elif chosen_result.result_id.startswith('cached_'):
        try:
            video_id = int(chosen_result.result_id.split('_')[1])
            video = await database.get_video_by_id(video_id)
            if video and video.get('file_id'):
                await database.update_video_file_id(video['url'], video['file_id'])
        except (ValueError, IndexError):
            pass