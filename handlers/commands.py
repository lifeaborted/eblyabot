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
        await message.answer('Отправьте ссылку на медиаконтент в этот чат, чтобы бот скачал его для вас.')

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
        f'Привет, {user.first_name}!\n'
        'Я бот для автоматического скачивания медиафайлов по ссылкам.\n\n'
        'Как мной пользоваться:\n'
        '— Отправьте прямую ссылку на публикацию или видео в этот чат.\n'
        '— Воспользуйтесь встроенным веб-приложением (кнопка "Сайт" слева от поля ввода).\n'
        '— Вы также можете добавить меня в любую группу и отправить ссылку, упомянув мой юзернейм.\n\n'
        'Для получения полного списка доступных команд введите /help',
        reply_markup=ReplyKeyboardRemove(remove_keyboard=True)
    )

@router.message(Command("history"))
async def history(message: Message):
    videos = await database.get_user_videos(message.from_user.id)
    if not videos:
        return await message.answer('У вас пока нет истории скачиваний.')

    lines = ["<b>История скачиваний:</b>"]
    for i, video in enumerate(videos[:10], 1):
        title = video.get('title', 'Медиафайл').replace('<', '').replace('>', '')
        url = video.get('url', 'Нет ссылки')
        lines.append(f"<b>{i}.</b> {title}\nСсылка: {url}")

    msg = "\n\n".join(lines)
    if len(videos) > 10:
        msg += f"\n\n<i>...и еще {len(videos) - 10} записей</i>"

    await message.answer(msg, reply_markup=ReplyKeyboardRemove(remove_keyboard=True), disable_web_page_preview=True)

@router.message(Command("stats"))
async def stats(message: Message):
    user_videos = await database.get_user_videos(message.from_user.id)
    total_videos = await database.get_total_videos()
    msg = (f'<b>Статистика бота:</b>\n\n'
           f'Ваши скачивания: {len(user_videos)}\n'
           f'Всего обработано ссылок: {total_videos}')
    await message.answer(msg, reply_markup=ReplyKeyboardRemove(remove_keyboard=True))


@router.message(Command("help"))
async def command_help(message: Message):
    help_text = (
        "<b>Доступные команды:</b>\n\n"
        "<b>Основные:</b>\n"
        "<code>/start</code> — перезапустить бота и показать приветственное сообщение\n"
        "<code>/help</code> — показать эту справку по командам\n"
        "<code>/history</code> — посмотреть историю ваших скачиваний (последние 10 записей)\n"
        "<code>/stats</code> — посмотреть общую статистику использования бота\n\n"
        "<b>Пересылка контента (автоотправка):</b>\n"
        "<code>/chats [ID]</code> — настроить автоматическую пересылку скачанных файлов в другие чаты или группы\n"
        "<code>/id</code> — узнать системный ID текущего чата (необходимо для команды /chats)\n\n"
        "<b>Как настроить пересылку в группу или канал:</b>\n"
        "1. Добавьте бота в нужную группу и дайте ему права на отправку сообщений.\n"
        "2. Напишите в этой группе команду <code>/id</code>, чтобы бот выдал вам её точный системный номер.\n"
        "3. Вернитесь в личные сообщения с ботом и отправьте этот ID: <code>/chats [номер]</code>\n\n"
        "Для настройки пересылки сразу в несколько чатов, перечислите их ID через запятую.\n"
        "Для полного отключения пересылки отправьте: <code>/chats 0</code>"
    )
    await message.answer(help_text)


@router.message(Command("id"))
async def get_chat_id(message: Message):
    await message.answer(f"ID этого чата: <code>{message.chat.id}</code>")


@router.message(Command("chats"))
async def configure_forward_chats(message: Message, command: CommandObject):
    args = command.args
    if not args:
        chats = await database.get_user_forward_chats(message.from_user.id)
        if chats:
            await message.answer(
                f"Текущие чаты для автоматической пересылки:\n<code>{', '.join(map(str, chats))}</code>\n\n"
                f"Чтобы очистить список, введите: <code>/chats 0</code>"
            )
        else:
            await message.answer(
                "Список чатов для автоматической пересылки пуст.\n\n"
                "Введите команду в формате:\n"
                "<code>/chats -1001234567, -1009876543</code>\n\n"
                "Для полной очистки: <code>/chats 0</code>"
            )
        return

    if args.strip() == '0':
        await database.set_user_forward_chats(message.from_user.id, "")
        await message.answer("Список чатов очищен. Теперь скачанные файлы отправляются только в текущий чат.")
        return

    raw_chats = args.replace(' ', '').split(',')
    valid_chats = []
    for c in raw_chats:
        try:
            valid_chats.append(int(c))
        except ValueError:
            pass

    if not valid_chats:
        await message.answer("Неверный формат. Пожалуйста, вводите только ID чатов (числа).")
        return

    chats_str = ",".join(map(str, valid_chats))
    await database.set_user_forward_chats(message.from_user.id, chats_str)
    await message.answer(
        f"Чаты для автоматической пересылки успешно сохранены!\n"
        f"Сохраненные ID:\n<code>{chats_str}</code>\n\n"
        f"Убедитесь, что бот добавлен в эти чаты в качестве администратора или имеет права на отправку файлов."
    )