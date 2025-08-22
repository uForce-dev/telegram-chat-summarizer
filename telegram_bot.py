import asyncio
import logging
import shlex
from collections import deque
from functools import wraps

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

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

MAX_HISTORY_SIZE = 200
chat_histories = {}


def get_db(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        db = SessionLocal()
        try:
            return await func(*args, db=db, **kwargs)
        finally:
            db.close()

    return wrapper


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для суммирования чатов. Добавьте меня в группу и дайте права на чтение сообщений.\n"
        "Для вызова справки используйте /help."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "**Как использовать бота:**\n\n"
        "1. Убедитесь, что бот добавлен в чат.\n"
        "2. Для суммирования вызовите команду:\n"
        "`/summarize <тип_промпта> [количество_сообщений]`\n\n"
        "   - `<тип_промпта>`: обязательный параметр. Указывает, какой системный промпт использовать (например, `general`). "
        "Посмотреть доступные типы можно в админ-панели.\n"
        "   - `[количество_сообщений]`: необязательный параметр. По умолчанию — **100**. Максимум — **200**.\n\n"
        "**Примеры:**\n"
        "- `/summarize general` — получить сводку по последним 100 сообщениям.\n"
        "- `/summarize meetings 50` — получить сводку по последним 50 сообщениям с промптом `meetings`."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


@get_db
async def summarize(
    update: Update, context: ContextTypes.DEFAULT_TYPE, db: Session = None
):
    user = update.effective_user
    chat_id = update.message.chat_id
    if not user:
        return

    try:
        parts = shlex.split(update.message.text)
        if not (2 <= len(parts) <= 3):
            raise ValueError

        prompt_type = parts[1]
        num_messages = int(parts[2]) if len(parts) == 3 else 100

    except (ValueError, IndexError):
        await update.message.reply_text(
            "Неверный формат команды. Используйте: `/summarize <тип_промпта> [кол-во сообщений]`\n"
            "Для справки введите /help."
        )
        return

    if num_messages <= 0 or num_messages > MAX_HISTORY_SIZE:
        await update.message.reply_text(
            f"Количество сообщений должно быть от 1 до {MAX_HISTORY_SIZE}."
        )
        return

    if not check_user_rate_limit(db, str(user.id)):
        await update.message.reply_text(
            f"Вы превысили лимит запросов ({settings.user_request_limit_per_hour} в час). Попробуйте позже."
        )
        return

    if not check_rate_limit(db, str(chat_id)):
        await update.message.reply_text(
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
        await update.message.reply_text(error_text, parse_mode="Markdown")
        return

    history = chat_histories.get(chat_id)
    if not history or len(history) < 10:
        await update.message.reply_text(
            "Недостаточно истории сообщений для анализа. Подождите, пока в чате появятся новые сообщения."
        )
        return

    messages_to_process = list(history)[-num_messages:]

    await update.message.reply_text(
        f"✅ Принято! Анализирую последние {len(messages_to_process)} сообщений. Это может занять несколько минут..."
    )

    is_sent = await process_summarization_request(
        bot=context.bot,
        chat_id=chat_id,
        messages=messages_to_process,
        user_name=user.username or user.first_name,
        system_prompt=prompt.text,
        reply_to_message_id=update.message.message_id,
    )

    if is_sent:
        update_rate_limit(db, str(chat_id))
        log_summary_request(db, user_id=str(user.id), root_post_id=str(chat_id))


async def store_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user = update.message.from_user
    username = user.username or user.full_name

    message_data = {
        "user": username,
        "text": update.message.text,
        "date": update.message.date.isoformat(),
    }

    if chat_id not in chat_histories:
        chat_histories[chat_id] = deque(maxlen=MAX_HISTORY_SIZE)

    chat_histories[chat_id].append(message_data)


def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    application = Application.builder().token(settings.telegram_bot_token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("summarize", summarize))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, store_message)
    )

    logger.info("Telegram-бот запущен в фоновом режиме...")
    application.run_polling()