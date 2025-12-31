"""
Бот "Без него" (@beznegbot)
Отправляет сообщения, которые видят все КРОМЕ указанных пользователей.

Использование (inline):
@beznegbot Привет всем! @excluded_user1 @excluded_user2

Команды в ЛС:
/start - приветствие и инструкция
/setmessage <текст> - установить кастомный текст отказа
/resetmessage - сбросить текст отказа на дефолтный
/settings - посмотреть текущие настройки
"""

import asyncio
import logging
import re
import uuid
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.enums import ParseMode
import aiosqlite

# ============== КОНФИГУРАЦИЯ ==============
BOT_TOKEN = "8478498738:AAGVuj_3DNqr8o27Y9TIegqmvikT1o4z2qc"
DATABASE_PATH = "bezneg_bot.db"
DEFAULT_REJECT_MESSAGE = "🚫 Это сообщение не для тебя"

# ============== ЛОГИРОВАНИЕ ==============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============== ИНИЦИАЛИЗАЦИЯ ==============
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


# ============== БАЗА ДАННЫХ ==============
async def init_db():
    """Инициализация базы данных"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Таблица настроек пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                reject_message TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица секретных сообщений
        await db.execute("""
            CREATE TABLE IF NOT EXISTS secret_messages (
                message_id TEXT PRIMARY KEY,
                sender_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                excluded_usernames TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.commit()
        logger.info("База данных инициализирована")


async def get_user_reject_message(user_id: int) -> str:
    """Получить кастомное сообщение отказа для пользователя"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT reject_message FROM user_settings WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        
        if row and row[0]:
            return row[0]
        return DEFAULT_REJECT_MESSAGE


async def set_user_reject_message(user_id: int, message: Optional[str]):
    """Установить кастомное сообщение отказа"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO user_settings (user_id, reject_message)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET reject_message = ?
        """, (user_id, message, message))
        await db.commit()


async def save_secret_message(message_id: str, sender_id: int, content: str, excluded: list[str]):
    """Сохранить секретное сообщение"""
    excluded_str = ",".join(excluded)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO secret_messages (message_id, sender_id, content, excluded_usernames)
            VALUES (?, ?, ?, ?)
        """, (message_id, sender_id, content, excluded_str))
        await db.commit()


async def get_secret_message(message_id: str) -> Optional[dict]:
    """Получить секретное сообщение по ID"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT sender_id, content, excluded_usernames FROM secret_messages WHERE message_id = ?",
            (message_id,)
        )
        row = await cursor.fetchone()
        
        if row:
            return {
                "sender_id": row[0],
                "content": row[1],
                "excluded_usernames": row[2].split(",") if row[2] else []
            }
        return None


# ============== ПАРСИНГ СООБЩЕНИЙ ==============
def parse_inline_query(query: str) -> tuple[str, list[str]]:
    """
    Парсит inline запрос и извлекает текст сообщения и список исключённых.
    
    Формат: "Текст сообщения @user1 @user2 @user3"
    Возвращает: (текст_сообщения, [user1, user2, user3])
    """
    # Находим все @username в конце строки
    # Username в Telegram: 5-32 символа, буквы, цифры, подчёркивания
    pattern = r'@([a-zA-Z][a-zA-Z0-9_]{4,31})'
    
    usernames = re.findall(pattern, query)
    
    # Убираем @usernames из текста (только те что в конце)
    # Идём с конца и убираем username'ы
    text = query.strip()
    for username in reversed(usernames):
        text = re.sub(rf'\s*@{username}\s*$', '', text, flags=re.IGNORECASE)
    
    text = text.strip()
    
    # Приводим username'ы к нижнему регистру для сравнения
    usernames_lower = [u.lower() for u in usernames]
    
    return text, usernames_lower


# ============== ОБРАБОТЧИКИ КОМАНД (ЛС) ==============
@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    welcome_text = """
👋 <b>Привет! Я бот "Без него"</b>

Я отправляю сообщения, которые видят <b>все, кроме</b> указанных людей.

<b>🔹 Как использовать:</b>
В любом чате напиши:
<code>@beznegbot Твоё сообщение @username1 @username2</code>

Сообщение увидят все, <b>кроме</b> @username1 и @username2.

<b>🔹 Команды:</b>
/setmessage &lt;текст&gt; — изменить текст, который видят исключённые
/resetmessage — сбросить текст на стандартный
/settings — посмотреть настройки

<b>🔹 Пример:</b>
<code>@beznegbot Го в кино вечером? @vasya</code>
Все увидят приглашение, кроме Васи 😏
"""
    await message.answer(welcome_text, parse_mode=ParseMode.HTML)
    logger.info(f"Пользователь {message.from_user.id} запустил бота")


@router.message(Command("setmessage"))
async def cmd_set_message(message: Message):
    """Установить кастомное сообщение отказа"""
    # Извлекаем текст после команды
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "⚠️ Укажи текст после команды.\n\n"
            "Пример: <code>/setmessage Тебе это видеть не положено!</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    new_message = args[1].strip()
    
    if len(new_message) > 200:
        await message.answer("⚠️ Слишком длинный текст. Максимум 200 символов.")
        return
    
    await set_user_reject_message(message.from_user.id, new_message)
    
    await message.answer(
        f"✅ Установлено новое сообщение для исключённых:\n\n<i>{new_message}</i>",
        parse_mode=ParseMode.HTML
    )
    logger.info(f"Пользователь {message.from_user.id} изменил сообщение отказа")


@router.message(Command("resetmessage"))
async def cmd_reset_message(message: Message):
    """Сбросить сообщение отказа на дефолтное"""
    await set_user_reject_message(message.from_user.id, None)
    
    await message.answer(
        f"✅ Сообщение сброшено на стандартное:\n\n<i>{DEFAULT_REJECT_MESSAGE}</i>",
        parse_mode=ParseMode.HTML
    )
    logger.info(f"Пользователь {message.from_user.id} сбросил сообщение отказа")


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    """Показать текущие настройки"""
    reject_msg = await get_user_reject_message(message.from_user.id)
    is_custom = reject_msg != DEFAULT_REJECT_MESSAGE
    
    settings_text = f"""
⚙️ <b>Твои настройки:</b>

<b>Сообщение для исключённых:</b>
<i>{reject_msg}</i>
{"(кастомное)" if is_custom else "(стандартное)"}
"""
    await message.answer(settings_text, parse_mode=ParseMode.HTML)


# ============== INLINE РЕЖИМ ==============
@router.inline_query()
async def inline_handler(inline_query: InlineQuery):
    """Обработчик inline запросов"""
    query_text = inline_query.query.strip()
    
    if not query_text:
        # Пустой запрос — показываем подсказку
        await inline_query.answer(
            results=[],
            switch_pm_text="Как пользоваться ботом?",
            switch_pm_parameter="help",
            cache_time=5
        )
        return
    
    # Парсим запрос
    message_text, excluded_usernames = parse_inline_query(query_text)
    
    if not message_text:
        # Нет текста сообщения
        result = InlineQueryResultArticle(
            id="no_text",
            title="⚠️ Введи текст сообщения",
            description="Формат: сообщение @исключённый1 @исключённый2",
            input_message_content=InputTextMessageContent(
                message_text="Ошибка: пустое сообщение"
            )
        )
        await inline_query.answer(results=[result], cache_time=5)
        return
    
    if not excluded_usernames:
        # Нет исключённых пользователей
        result = InlineQueryResultArticle(
            id="no_excluded",
            title="⚠️ Укажи кого исключить",
            description="Добавь @username в конце сообщения",
            input_message_content=InputTextMessageContent(
                message_text="Ошибка: не указаны исключённые"
            )
        )
        await inline_query.answer(results=[result], cache_time=5)
        return
    
    # Генерируем уникальный ID для сообщения
    message_id = str(uuid.uuid4())[:8]
    
    # Сохраняем сообщение в БД
    await save_secret_message(
        message_id=message_id,
        sender_id=inline_query.from_user.id,
        content=message_text,
        excluded=excluded_usernames
    )
    
    # Формируем текст превью
    excluded_display = ", ".join([f"@{u}" for u in excluded_usernames])
    
    if len(excluded_usernames) == 1:
        preview_title = f"🔒 Сообщение (без @{excluded_usernames[0]})"
    else:
        preview_title = f"🔒 Сообщение (исключены: {len(excluded_usernames)} чел.)"
    
    # Текст который будет отправлен в чат
    public_text = f"🔒 <b>Секретное сообщение</b>\n\n<i>Не для: {excluded_display}</i>"
    
    # Кнопка для просмотра
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👀 Показать сообщение", callback_data=f"show:{message_id}")]
        ]
    )
    
    result = InlineQueryResultArticle(
        id=message_id,
        title=preview_title,
        description=f"📝 {message_text[:50]}{'...' if len(message_text) > 50 else ''}",
        input_message_content=InputTextMessageContent(
            message_text=public_text,
            parse_mode=ParseMode.HTML
        ),
        reply_markup=keyboard
    )
    
    await inline_query.answer(results=[result], cache_time=1, is_personal=True)
    logger.info(f"Inline запрос от {inline_query.from_user.id}: исключены {excluded_usernames}")


# ============== CALLBACK (НАЖАТИЕ КНОПКИ) ==============
@router.callback_query(F.data.startswith("show:"))
async def callback_show_message(callback: CallbackQuery):
    """Обработчик нажатия на кнопку 'Показать сообщение'"""
    message_id = callback.data.split(":")[1]
    
    # Получаем сообщение из БД
    secret = await get_secret_message(message_id)
    
    if not secret:
        await callback.answer("❌ Сообщение не найдено или устарело", show_alert=True)
        return
    
    # Проверяем username нажавшего
    user = callback.from_user
    user_username = user.username.lower() if user.username else None
    
    # Проверяем, исключён ли пользователь
    if user_username and user_username in secret["excluded_usernames"]:
        # Пользователь исключён — показываем сообщение отказа
        reject_message = await get_user_reject_message(secret["sender_id"])
        await callback.answer(reject_message, show_alert=True)
        logger.info(f"Пользователь @{user_username} попытался прочитать сообщение {message_id} — отказано")
    else:
        # Показываем сообщение
        await callback.answer(secret["content"], show_alert=True)
        logger.info(f"Пользователь {user.id} прочитал сообщение {message_id}")


# ============== ЗАПУСК ==============
async def main():
    """Главная функция запуска бота"""
    logger.info("Инициализация бота...")
    
    # Инициализируем БД
    await init_db()
    
    # Запускаем polling
    logger.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
