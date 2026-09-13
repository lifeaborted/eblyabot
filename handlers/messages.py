import os
import re
import json
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, FSInputFile, InputMediaPhoto
from downloaders.factory import DownloaderFactory
from utils.cleanup import temp_files_cleanup
from config import DOWNLOAD_DIR
import database

logger = logging.getLogger(__name__)
router = Router()

URL_REGEX = re.compile(r'https?://(?:www\.|vm\.|vt\.|m\.)?(?:tiktok\.com|youtube\.com|youtu\.be)/[^\s]+', re.IGNORECASE)


def chunk_list(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


@router.message(F.text | F.caption)
async def handle_message(message: Message, bot: Bot):
    text = (message.text or message.caption).strip()
    user_id = message.from_user.id

    # === ЛОГИРОВАНИЕ ВХОДЯЩЕГО СООБЩЕНИЯ ===
    logger.info(f"--- [USER: {user_id}] Входящее сообщение: {text} ---")

    is_private = message.chat.type == 'private'
    is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == bot.id
    me = await bot.get_me()
    is_mentioned = me.username and (f"@{me.username.lower()}" in text.lower())
    is_via_bot = message.via_bot and message.via_bot.id == bot.id

    if not (is_private or is_reply_to_bot or is_mentioned or is_via_bot):
        logger.info(f"[USER: {user_id}] Игнорирую (сообщение не подходит по контексту чата).")
        return

    match = URL_REGEX.search(text)
    if not match:
        logger.info(f"[USER: {user_id}] В тексте не найдена поддерживаемая ссылка.")
        if is_private:
            await message.answer('Пожалуйста, отправьте ссылку на TikTok или YouTube.')
        return

    url = match.group(0)
    logger.info(f"[USER: {user_id}] Найдена ссылка: {url}")
    status_msg = await message.answer('Начинаю скачивание...')

    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"[USER: {user_id}] Не удалось удалить оригинальное сообщение: {e}")

    existing = await database.get_video_by_url(url)
    if existing:
        logger.info(f"[USER: {user_id}] Файл найден в БД (Кэш). Выгружаем...")
        await send_from_cache(message, bot, url, existing, status_msg)
        return

    downloader = DownloaderFactory.get(url, DOWNLOAD_DIR)
    if not downloader:
        logger.error(f"[USER: {user_id}] Загрузчик не найден для {url}")
        return await status_msg.edit_text("Этот сервис не поддерживается. Отправьте ссылку на TikTok или YouTube.")

    async def progress_cb(percent_or_text, speed=None, eta=None):
        try:
            if isinstance(percent_or_text, str):
                await status_msg.edit_text(percent_or_text)
            else:
                bar_len = 10
                filled = int(round(bar_len * percent_or_text / 100))
                bar = '█' * filled + '░' * (bar_len - filled)
                await status_msg.edit_text(
                    f"Загрузка файла...\n\n<code>[{bar}] {percent_or_text:.1f}%</code>\nСкорость: <code>{speed}</code> | Осталось: <code>{eta}</code>"
                )
        except Exception:
            pass

    logger.info(f"[USER: {user_id}] Старт скачивания через {type(downloader).__name__}...")
    result = await downloader.download(url, progress_callback=progress_cb)

    if not result.get('success'):
        error_text = result.get('error', 'неизвестная ошибка')
        logger.error(f"[USER: {user_id}] ОШИБКА ЗАГРУЗКИ: {error_text}")
        return await status_msg.edit_text(f"Не удалось скачать файл: {error_text}", parse_mode=None)

    media_type = result.get('media_type', 'video')
    title = result.get('title', 'Медиа')
    safe_title = (title[:1000] + '...') if len(title) > 1000 else title

    logger.info(f"[USER: {user_id}] Скачивание завершено. Тип: {media_type}, Заголовок: {title}")

    cleanup_paths = [result.get('file_path')] if media_type == 'video' else result.get('image_paths', [])
    if result.get('audio_path'):
        cleanup_paths.append(result.get('audio_path'))

    async with temp_files_cleanup(cleanup_paths):
        if media_type == 'images':
            logger.info(f"[USER: {user_id}] Отправляю фото-карусель (картинок: {len(result['image_paths'])})...")
            await status_msg.edit_text('Отправляю слайдшоу...')
            saved_file_ids = []

            for chunk_idx, chunk in enumerate(chunk_list(result['image_paths'], 10)):
                media_group = []
                for idx, img_path in enumerate(chunk):
                    caption = safe_title if (chunk_idx == len(result['image_paths']) // 10 and idx == 0) else None
                    media_group.append(InputMediaPhoto(type='photo', media=FSInputFile(img_path), caption=caption))

                msgs = await bot.send_media_group(message.chat.id, media=media_group)
                saved_file_ids.extend([m.photo[-1].file_id for m in msgs if m.photo])

            if result.get('audio_path') and os.path.exists(result['audio_path']):
                logger.info(f"[USER: {user_id}] Отправляю аудиодорожку...")
                await message.answer_audio(audio=FSInputFile(result['audio_path']), caption="Оригинальный звук")

            await database.add_video(url=url, user_id=user_id, username=message.from_user.username,
                                     file_path=result['image_paths'][0] if result['image_paths'] else None,
                                     file_id=json.dumps(saved_file_ids) if saved_file_ids else None, title=title,
                                     media_type='images')
            logger.info(f"[USER: {user_id}] Слайдшоу успешно отправлено и занесено в БД.")
        else:
            logger.info(f"[USER: {user_id}] Отправляю видеофайл...")
            await status_msg.edit_text('Отправляю видео...')
            sent = await message.answer_video(video=FSInputFile(result['file_path']), caption=safe_title)
            await database.add_video(url=url, user_id=user_id, username=message.from_user.username,
                                     file_path=result['file_path'], file_id=sent.video.file_id, title=title,
                                     media_type='video')
            logger.info(f"[USER: {user_id}] Видео успешно отправлено и занесено в БД.")

    await status_msg.delete()


async def send_from_cache(message: Message, bot: Bot, url: str, media_data: dict, status_msg: Message):
    user_id = message.from_user.id
    title = media_data.get('title', 'Медиа')
    safe_title = (title[:1000] + '...') if len(title) > 1000 else title
    file_id = media_data.get('file_id')

    try:
        if media_data.get('media_type') == 'images' and file_id:
            logger.info(f"[USER: {user_id}] Выгрузка слайдшоу по File ID...")
            file_ids = json.loads(file_id) if file_id.startswith('[') else [file_id]
            for chunk_idx, chunk in enumerate(chunk_list(file_ids, 10)):
                media_group = [InputMediaPhoto(type='photo', media=fid,
                                               caption=safe_title if (chunk_idx == 0 and idx == 0) else None) for
                               idx, fid in enumerate(chunk)]
                await bot.send_media_group(message.chat.id, media=media_group)
            logger.info(f"[USER: {user_id}] Слайдшоу из кэша отправлено.")

        elif file_id:
            logger.info(f"[USER: {user_id}] Выгрузка видео по File ID: {file_id}")
            await message.answer_video(video=file_id, caption=safe_title)
            await database.update_video_file_id(url, file_id)
            logger.info(f"[USER: {user_id}] Видео из кэша отправлено.")
        else:
            logger.warning(f"[USER: {user_id}] Запись в кэше есть, но File ID отсутствует!")
            return await status_msg.edit_text('Файл не найден. Пожалуйста, отправьте ссылку еще раз.')

        await status_msg.delete()
    except Exception as e:
        logger.error(f"[USER: {user_id}] Ошибка отправки из кэша: {e}")
        await status_msg.edit_text('Произошла ошибка при выгрузке из кэша. Пожалуйста, отправьте ссылку еще раз.')