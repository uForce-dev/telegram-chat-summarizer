import asyncio
import logging
import shlex
from functools import wraps

from sqlalchemy.orm import Session
from telethon import TelegramClient, events

from app.database import SessionLocal
from app.loader import settings
from app.services import prompt as prompt_service
from app.services.logging import log_summary_request
from app.services.summarization import (
    check_user_rate_limit,
    process_summarization_request,
    update_rate_limit,
    check_rate_limit,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --- Telethon Client (только создаем экземпляр, не запускаем) ---
# Это позволяет нам использовать декораторы @bot.on ниже
bot = TelegramClient(
    'bot', settings.telegram_api_id, settings.telegram_api_hash
)


def get_db(func):
    @wraps(func)
    async def wrapper(event):
        db = SessionLocal()
        try:
            return await func(event, db=db)
        finally:
            db.close()

    return wrapper


@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply(
        "Привет! Я бот для суммирования чатов. Добавьте меня в группу и дайте права на чтение сообщений.\n"
        "Для вызова справки используйте /help."
    )


@bot.on(events.NewMessage(pattern='/help'))
async def help_command(event):
    help_text = (
        "**Как использовать бота:**\n\n"
        "1. Убедитесь, что бот добавлен в чат.\n"
        "2. Для суммирования вызовите команду:\n"
        "`/summarize <тип_промпта> [количество_сообщений]`\n\n"
        "   - `<тип_промпта>`: обязательный параметр. Указывает, какой системный промпт использовать (например, `general`).\n"
        "   - `[количество_сообщений]`: необязательный параметр. По умолчанию — **100**. Максимум — **200**.\n\n"
        "**Примеры:**\n"
        "- `/summarize general` — получить сводку по последним 100 сообщениям.\n"
        "- `/summarize meetings 50` — получить сводку по последним 50 сообщениям с промптом `meetings`."
    )
    await event.reply(help_text, parse_mode="md")


@bot.on(events.NewMessage(pattern='/summarize'))
@get_db
async def summarize(event, db: Session = None):
    user = await event.get_sender()
    chat_id = event.chat_id

    try:
        parts = shlex.split(event.message.text)
        if not (2 <= len(parts) <= 3):
            raise ValueError

        prompt_type = parts[1]
        num_messages = int(parts[2]) if len(parts) == 3 else 100

    except (ValueError, IndexError):
        await event.reply(
            "Неверный формат команды. Используйте: `/summarize <тип_промпта> [кол-во сообщений]`\n"
            "Для справки введите /help."
        )
        return

    if not (0 < num_messages <= 200):
        await event.reply("Количество сообщений должно быть от 1 до 200.")
        return

    if not check_user_rate_limit(db, str(user.id)):
        await event.reply(
            f"Вы превысили лимит запросов ({settings.user_request_limit_per_hour} в час). Попробуйте позже."
        )
        return

    if not check_rate_limit(db, str(chat_id)):
        await event.reply(
            f"Для этого чата суммирование было недавно. Попробуйте через {settings.thread_request_cooldown_hours}ч."
        )
        return

    prompt = prompt_service.get_prompt_by_name(db, prompt_type)
    if not prompt:
        all_prompts = prompt_service.get_all_prompts(db)
        error_text = f"Тип промпта '{prompt_type}' не найден."
        if all_prompts:
            available_types = ", ".join(f"`{p.name}`" for p in all_prompts)
            error_text += f"\n\nДоступные типы: {available_types}"
        await event.reply(error_text, parse_mode="md")
        return

    await event.reply(
        f"✅ Принято! Анализирую последние {num_messages} сообщений. Это может занять несколько минут..."
    )

    messages = await bot.get_messages(event.chat_id, limit=num_messages)
    messages_to_process = []
    for message in reversed(messages):
        if message.text:
            sender = await message.get_sender()
            username = sender.username or sender.first_name or "Unknown"
            messages_to_process.append(
                {
                    "user": username,
                    "text": message.text,
                    "date": message.date.isoformat(),
                }
            )

    if len(messages_to_process) < 10:
        await event.reply(
            "Недостаточно истории сообщений для анализа. Подождите, пока в чате появятся новые сообщения."
        )
        return

    is_sent = await process_summarization_request(
        bot=bot,
        chat_id=chat_id,
        messages=messages_to_process,
        user_name=user.username or user.first_name,
        system_prompt=prompt.text,
        reply_to_message_id=event.message.id,
    )

    if is_sent:
        update_rate_limit(db, str(chat_id))
        log_summary_request(db, user_name=user.username or user.first_name, root_post_id=str(chat_id))


def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def main():
        await bot.start(bot_token=settings.telegram_bot_token)
        logger.info("Telegram-бот запущен...")
        await bot.run_until_disconnected()

    loop.run_until_complete(main())