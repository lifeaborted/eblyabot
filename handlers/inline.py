import uuid
import json
import logging
from aiogram import Router
from aiogram.types import (
    InlineQuery, ChosenInlineResult, InlineQueryResultCachedVideo,
    InlineQueryResultCachedPhoto, InlineQueryResultArticle,
    InputTextMessageContent, InlineQueryResultsButton
)
import database

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
                    parsed = json.loads(video['file_id'])
                    photo_file_id = None
                    if isinstance(parsed, dict) and parsed.get("photos"):
                        photo_file_id = parsed["photos"][0]
                    elif isinstance(parsed, list) and parsed:
                        photo_file_id = parsed[0]

                    if photo_file_id:
                        clean_title = video.get('title', 'Слайдшоу').replace('<b>', '').replace('</b>', '').split('\n')[0]
                        results.append(InlineQueryResultCachedPhoto(
                            id=result_id,
                            photo_file_id=photo_file_id,
                            title=f"Слайдшоу: {clean_title}",
                            description="Отправится обложка и ссылка",
                            caption=f"{video.get('title', '')}\n\nСмотреть полностью: {video['url']}"
                        ))
                except json.JSONDecodeError:
                    pass
            else:
                results.append(InlineQueryResultCachedVideo(
                    id=result_id,
                    video_file_id=video['file_id'],
                    title="Видеофайл"
                ))
    elif any(d in query.lower() for d in ['tiktok.com', 'youtube.com', 'youtu.be']):
        existing_video = await database.get_video_by_url(query)
        if existing_video and existing_video.get('file_id'):
            if existing_video.get('media_type') == 'images':
                try:
                    parsed = json.loads(existing_video['file_id'])
                    photo_file_id = None
                    if isinstance(parsed, dict) and parsed.get("photos"):
                        photo_file_id = parsed["photos"][0]
                    elif isinstance(parsed, list) and parsed:
                        photo_file_id = parsed[0]

                    if photo_file_id:
                        results.append(InlineQueryResultCachedPhoto(
                            id=str(uuid.uuid4()),
                            photo_file_id=photo_file_id,
                            title="Отправить обложку слайдшоу",
                            caption=f"{existing_video.get('title', '')}\n\nСмотреть полностью: {existing_video['url']}"
                        ))
                except json.JSONDecodeError:
                    pass
            else:
                results.append(InlineQueryResultCachedVideo(
                    id=str(uuid.uuid4()),
                    video_file_id=existing_video['file_id'],
                    title="Отправить видео"
                ))

        if not results:
            if inline_query.chat_type == 'sender':
                button_config = InlineQueryResultsButton(text="Скачать новое видео в ЛС", start_parameter="new_download")
            else:
                results.append(InlineQueryResultArticle(
                    id=str(uuid.uuid4()),
                    title="Скачать в этот чат",
                    description="Нажмите для начала загрузки",
                    input_message_content=InputTextMessageContent(message_text=query, parse_mode=None)
                ))

    await inline_query.answer(results, cache_time=0, is_personal=True, button=button_config)

@router.chosen_inline_result()
async def chosen_inline_result_handler(chosen_result: ChosenInlineResult):
    query = chosen_result.query
    if any(d in query.lower() for d in ['tiktok.com', 'youtube.com', 'youtu.be']):
        video = await database.get_video_by_url(query)
        if video and video.get('file_id'):
            await database.update_video_file_id(video['url'], video['file_id'])