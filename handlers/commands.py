import os
from aiogram import Router, Bot
from aiogram.types import Message, MenuButtonWebApp, WebAppInfo, ReplyKeyboardRemove
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import FSInputFile
from config import ADMIN_ID, SERVER_URL
import database
import logging
logger = logging.getLogger(__name__)
router = Router()

@router.message(CommandStart(deep_link=True))
async def start_new_download(message: Message, command: CommandObject):
    if command.args == 'new_download':
        await message.answer('Отправьте ссылку в этот чат, чтобы видео стало доступно через бота в любых чатах.')

@router.message(CommandStart())
async def start_normal(message: Message, bot: Bot):
    user = message.from_user
    normal_url = f"{SERVER_URL}/?user_id={user.id}&username={user.username or 'unknown'}"

    try:
        await bot.set_chat_menu_button(
            chat_id=user.id,
            menu_button=MenuButtonWebApp(type="web_app", text="Сайт", web_app=WebAppInfo(url=normal_url))
        )
    except Exception as e:
        logger.error(f"Error setting menu button: {e}")

    await message.answer(
        f'Привет, {user.first_name}!\n\n'
        'Как пользоваться:\n'
        '— Отправьте ссылку на видео в этот чат\n'
        '— Воспользуйтесь кнопкой сайта\n'
        '— Добавьте бота в группу и тегните его вместе со ссылкой',
        reply_markup=ReplyKeyboardRemove(remove_keyboard=True)
    )

@router.message(Command("history"))
async def history(message: Message):
    videos = await database.get_user_videos(message.from_user.id)
    if not videos:
        return await message.answer('У вас пока нет истории скачиваний.')

    lines = ["<b>История скачиваний:</b>"]
    for i, video in enumerate(videos[:10], 1):
        title = video.get('title', 'Видео').replace('<', '').replace('>', '')
        url = video.get('url', 'Нет ссылки')
        lines.append(f"<b>{i}.</b> {title}\nСсылка: {url}")

    msg = "\n\n".join(lines)
    if len(videos) > 10:
        msg += f"\n\n<i>...и еще {len(videos) - 10} видео</i>"

    await message.answer(msg, reply_markup=ReplyKeyboardRemove(remove_keyboard=True), disable_web_page_preview=True)

@router.message(Command("stats"))
async def stats(message: Message):
    user_videos = await database.get_user_videos(message.from_user.id)
    total_videos = await database.get_total_videos()
    msg = (f'Статистика бота:\n\n'
           f'Ваши скачивания: {len(user_videos)}\n'
           f'Всего загрузок: {total_videos}')
    await message.answer(msg, reply_markup=ReplyKeyboardRemove(remove_keyboard=True))

@router.message(Command("help"))
async def help_command(message: Message):
    await message.answer('/start — Начать работу\n/history — История скачиваний\n/stats — Статистика', reply_markup=ReplyKeyboardRemove(remove_keyboard=True))

@router.message(Command("logs"))
async def get_logs(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    log_path = 'bot.log'
    if os.path.exists(log_path) and os.path.getsize(log_path) > 0:
        await message.answer_document(
            document=FSInputFile(log_path),
            caption="Логи за последние 24 часа"
        )
    else:
        await message.answer("Файл логов пуст или еще не создан.")