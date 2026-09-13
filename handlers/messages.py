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
from utils.url_resolver import resolve_url
from utils.format import format_caption

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

    logger.info(f"--- [USER: {user_id}] Входящее сообщение: {text} ---")

    is_private = message.chat.type == 'private'
    is_reply_to_bot = message.reply_to_message and message.reply_to_message.from_user.id == bot.id
    me = await bot.get_me()
    is_mentioned = me.username and (f"@{me.username.lower()}" in text.lower())
    is_via_bot = message.via_bot and message.via_bot.id == bot.id

    if not (is_private or is_reply_to_bot or is_mentioned or is_via_bot):
        return

    match = URL_REGEX.search(text)
    if not match:
        if is_private:
            await message.answer('Пожалуйста, отправьте ссылку на TikTok или YouTube.')
        return

    url = match.group(0)
    logger.info(f"[USER: {user_id}] Найдена ссылка: {url}")
    status_msg = await message.answer('Начинаю скачивание...')

    try:
        await message.delete()
    except Exception:
        pass

    resolved_url = await resolve_url(url)

    existing = await database.get_video_by_url(resolved_url)
    if existing:
        logger.info(f"[USER: {user_id}] Файл найден в БД. Выгружаем кэш...")
        await send_from_cache(message, bot, resolved_url, existing, status_msg)
        return

    downloader = DownloaderFactory.get(resolved_url, DOWNLOAD_DIR)
    if not downloader:
        logger.error(f"[USER: {user_id}] Загрузчик не найден для {url}")
        return await status_msg.edit_text("Этот сервис не поддерживается.")

    async def progress_cb(percent_or_text, speed=None, eta=None):
        try:
            if isinstance(percent_or_text, str):
                await status_msg.edit_text(percent_or_text)
            else:
                bar_len = 10
                filled = int(round(bar_len * percent_or_text / 100))
                bar = '█' * filled + '░' * (bar_len - filled)
                await status_msg.edit_text(
                    f"Загрузка...\n\n<code>[{bar}] {percent_or_text:.1f}%</code>\nСкорость: <code>{speed}</code> | Осталось: <code>{eta}</code>"
                )
        except Exception:
            pass

    logger.info(f"[USER: {user_id}] Старт скачивания через {type(downloader).__name__}...")
    result = await downloader.download(resolved_url, progress_callback=progress_cb)

    if not result.get('success'):
        error_text = result.get('error', 'неизвестная ошибка')
        logger.error(f"[USER: {user_id}] ОШИБКА ЗАГРУЗКИ: {error_text}")
        return await status_msg.edit_text(f"Не удалось скачать файл: {error_text}", parse_mode=None)

    media_type = result.get('media_type', 'video')
    uploader_name = result.get('uploader', 'Unknown')

    safe_caption = format_caption(
        uploader_name,
        result.get('title', ''),
        result.get('description', ''),
        result.get('tags', [])
    )

    logger.info(f"[USER: {user_id}] Скачивание завершено. Тип: {media_type}")

    cleanup_paths = [result.get('file_path')] if media_type == 'video' else result.get('image_paths', [])
    if result.get('audio_path'):
        cleanup_paths.append(result.get('audio_path'))

    async with temp_files_cleanup(cleanup_paths):
        if media_type == 'images':
            logger.info(f"[USER: {user_id}] Отправляю фото-карусель (картинок: {len(result['image_paths'])})...")
            await status_msg.edit_text('Отправляю слайдшоу...')
            saved_file_ids = []
            audio_file_id = None

            for chunk_idx, chunk in enumerate(chunk_list(result['image_paths'], 10)):
                media_group = []
                for idx, img_path in enumerate(chunk):
                    caption = safe_caption if (chunk_idx == 0 and idx == 0) else None
                    media_group.append(InputMediaPhoto(type='photo', media=FSInputFile(img_path), caption=caption))

                current_group = list(media_group)
                while current_group:
                    try:
                        msgs = await bot.send_media_group(message.chat.id, media=current_group)
                        saved_file_ids.extend([m.photo[-1].file_id for m in msgs if m.photo])
                        break
                    except Exception as e:
                        err_str = str(e)
                        match = re.search(r'failed to send message #(\d+)', err_str)
                        if match and "IMAGE_PROCESS_FAILED" in err_str:
                            bad_idx = int(match.group(1)) - 1
                            if 0 <= bad_idx < len(current_group):
                                logger.warning(f"Удаляю битое фото (индекс {bad_idx})")
                                current_group.pop(bad_idx)
                                if len(current_group) == 1:
                                    item = current_group[0]
                                    msg = await bot.send_photo(message.chat.id, photo=item.media, caption=item.caption)
                                    saved_file_ids.append(msg.photo[-1].file_id)
                                    break
                                continue
                        break

            if result.get('audio_path') and os.path.exists(result['audio_path']):
                try:
                    logger.info(f"[USER: {user_id}] Отправляю аудиодорожку...")
                    audio_msg = await message.answer_audio(
                        audio=FSInputFile(result['audio_path']),
                        caption="Оригинальный звук",
                        title="Оригинальный звук",
                        performer=uploader_name
                    )
                    audio_file_id = audio_msg.audio.file_id
                except Exception as e:
                    logger.error(f"[USER: {user_id}] Ошибка отправки аудио: {e}")

            forward_chats = await database.get_user_forward_chats(user_id)
            if forward_chats and (saved_file_ids or audio_file_id):
                for f_chat in forward_chats:
                    if f_chat == message.chat.id: continue
                    try:
                        if saved_file_ids:
                            for chunk_idx, chunk in enumerate(chunk_list(saved_file_ids, 10)):
                                mg = []
                                for idx, fid in enumerate(chunk):
                                    cap = safe_caption if (chunk_idx == 0 and idx == 0) else None
                                    mg.append(InputMediaPhoto(type='photo', media=fid, caption=cap))

                                if len(mg) == 1:
                                    await bot.send_photo(f_chat, photo=mg[0].media, caption=mg[0].caption)
                                else:
                                    await bot.send_media_group(f_chat, media=mg)
                        if audio_file_id:
                            await bot.send_audio(f_chat, audio=audio_file_id, caption="Оригинальный звук",
                                                 title="Оригинальный звук", performer=uploader_name)
                    except Exception as e:
                        logger.error(f"[USER: {user_id}] Ошибка пересылки слайдшоу в {f_chat}: {e}")
                        await message.answer(
                            f"Не удалось переслать контент в чат {f_chat}. Убедитесь, что бот имеет права на отправку сообщений.")

            if saved_file_ids or audio_file_id:
                cache_data = {"photos": saved_file_ids, "audio": audio_file_id}
                await database.add_video(url=resolved_url, user_id=user_id, username=message.from_user.username,
                                         file_path=result['image_paths'][0] if result.get('image_paths') else None,
                                         file_id=json.dumps(cache_data), title=safe_caption, media_type='images')
                logger.info(f"[USER: {user_id}] Слайдшоу и аудио успешно сохранены в БД.")
        else:
            logger.info(f"[USER: {user_id}] Отправляю видеофайл...")
            await status_msg.edit_text('Отправляю видео...')
            sent = await message.answer_video(video=FSInputFile(result['file_path']), caption=safe_caption)
            video_file_id = sent.video.file_id

            forward_chats = await database.get_user_forward_chats(user_id)
            if forward_chats:
                for f_chat in forward_chats:
                    if f_chat == message.chat.id: continue
                    try:
                        await bot.send_video(f_chat, video=video_file_id, caption=safe_caption)
                    except Exception as e:
                        logger.error(f"[USER: {user_id}] Ошибка пересылки видео в {f_chat}: {e}")
                        await message.answer(f"Не удалось переслать видео в чат {f_chat}.")

            await database.add_video(url=resolved_url, user_id=user_id, username=message.from_user.username,
                                     file_path=result['file_path'], file_id=video_file_id,
                                     title=safe_caption, media_type='video')
            logger.info(f"[USER: {user_id}] Видео успешно отправлено и занесено в БД.")

    await status_msg.delete()


async def send_from_cache(message: Message, bot: Bot, url: str, media_data: dict, status_msg: Message):
    user_id = message.from_user.id
    safe_caption = media_data.get('title', 'Медиа')
    file_id = media_data.get('file_id')

    forward_chats = await database.get_user_forward_chats(user_id)
    target_chats = [message.chat.id] + [c for c in forward_chats if c != message.chat.id]

    try:
        if media_data.get('media_type') == 'images' and file_id:
            logger.info(f"[USER: {user_id}] Выгрузка слайдшоу по File ID...")

            try:
                parsed_data = json.loads(file_id)
                if isinstance(parsed_data, dict):
                    photo_ids = parsed_data.get("photos", [])
                    audio_id = parsed_data.get("audio")
                elif isinstance(parsed_data, list):
                    photo_ids = parsed_data
                    audio_id = None
                else:
                    photo_ids = [file_id]
                    audio_id = None
            except json.JSONDecodeError:
                photo_ids = [file_id]
                audio_id = None

            for chat_id in target_chats:
                try:
                    if photo_ids:
                        for chunk_idx, chunk in enumerate(chunk_list(photo_ids, 10)):
                            media_group = [InputMediaPhoto(type='photo', media=fid, caption=safe_caption if (
                                        chunk_idx == 0 and idx == 0) else None) for idx, fid in enumerate(chunk)]
                            if len(media_group) == 1:
                                await bot.send_photo(chat_id, photo=media_group[0].media,
                                                     caption=media_group[0].caption)
                            else:
                                await bot.send_media_group(chat_id, media=media_group)

                    if audio_id:
                        await bot.send_audio(chat_id, audio=audio_id, caption="Оригинальный звук")
                except Exception as e:
                    if chat_id != message.chat.id:
                        await message.answer(f"Ошибка пересылки контента в чат {chat_id}.")
                    else:
                        raise e

            logger.info(f"[USER: {user_id}] Слайдшоу из кэша отправлено всем получателям.")
            await status_msg.delete()

        elif file_id:
            logger.info(f"[USER: {user_id}] Выгрузка видео по File ID: {file_id}")
            for chat_id in target_chats:
                try:
                    await bot.send_video(chat_id, video=file_id, caption=safe_caption)
                except Exception as e:
                    if chat_id != message.chat.id:
                        await message.answer(f"Ошибка пересылки контента в чат {chat_id}.")
                    else:
                        raise e

            await database.update_video_file_id(url, file_id)
            logger.info(f"[USER: {user_id}] Видео из кэша отправлено всем получателям.")
            await status_msg.delete()
        else:
            logger.warning(f"[USER: {user_id}] Запись в кэше есть, но File ID отсутствует!")
            return await status_msg.edit_text('Файл не найден. Пожалуйста, отправьте ссылку еще раз.')

    except Exception as e:
        logger.error(f"[USER: {user_id}] Ошибка отправки из кэша: {e}")
        await status_msg.edit_text('Произошла ошибка при выгрузке из кэша. Пожалуйста, отправьте ссылку еще раз.')