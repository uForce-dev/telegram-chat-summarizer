import asyncio
import logging
import shlex
from functools import wraps

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from app.database import SessionLocal
from app.loader import settings
from app.services import prompt as prompt_service
from app.services.summarization import (
    check_user_rate_limit,
    process_summarization_request,
    update_rate_limit,
)
from app.services.telegram import get_thread_messages, parse_message_link

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_db(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        db = SessionLocal()
        try:
            return await func(*args, db=db, **kwargs)
        finally:
            db.close()

    return wrapper


@get_db
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, db: Session = None):
    await update.message.reply_text("Привет! Я бот для суммирования тредов в Telegram.")


@get_db
async def summarize(
    update: Update, context: ContextTypes.DEFAULT_TYPE, db: Session = None
):
    user = update.effective_user
    if not user:
        return

    try:
        parts = shlex.split(update.message.text)
        if len(parts) != 3:
            raise ValueError
        _, prompt_type, message_link = parts
    except ValueError:
        await update.message.reply_text(
            "Неверный формат команды. Используйте: `/summarize <тип_промпта> <ссылка_на_сообщение>`"
        )
        return

    if not check_user_rate_limit(db, str(user.id)):
        await update.message.reply_text(
            f"Вы превысили лимит запросов ({settings.USER_REQUEST_LIMIT_PER_HOUR} в час). Попробуйте позже."
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

    parsed_link = parse_message_link(message_link)
    if not parsed_link:
        await update.message.reply_text("Не удалось распознать ссылку на сообщение.")
        return

    chat_id = parsed_link["chat_id"]
    message_id = parsed_link["message_id"]

    await update.message.reply_text("✅ Команда принята! Начинаю обработку...")

    thread_messages = await get_thread_messages(context.bot, chat_id, message_id)
    is_sent = process_summarization_request(
        bot=context.bot,
        chat_id=update.message.chat_id,
        thread_messages=thread_messages,
        user_name=user.username or user.first_name,
        system_prompt=prompt.text,
        reply_to_message_id=update.message.message_id,
    )
    if is_sent:
        thread_id = f"{chat_id}_{message_id}"
        update_rate_limit(db, thread_id)


def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    application = Application.builder().token(settings.telegram_bot_token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("summarize", summarize))

    application.run_polling()