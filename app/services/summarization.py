import asyncio
import logging
from datetime import datetime, UTC, timedelta

import tiktoken
from sqlalchemy.orm import Session
from telegram.constants import ParseMode
from telegram.error import TelegramError

from app.loader import settings
from app.models import ChatSummary, LogEntry
from app.services.openai import get_summary_from_openai

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096


async def send_message_in_chunks(bot, chat_id, text, reply_to_id):
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_id,
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    parts = []
    while len(text) > 0:
        if len(text) > TELEGRAM_MESSAGE_LIMIT:
            part = text[:TELEGRAM_MESSAGE_LIMIT]
            last_newline = part.rfind("\n")
            if last_newline != -1:
                parts.append(part[:last_newline])
                text = text[last_newline + 1 :]
            else:
                parts.append(part)
                text = text[TELEGRAM_MESSAGE_LIMIT:]
        else:
            parts.append(text)
            break

    for part in parts:
        await bot.send_message(
            chat_id=chat_id,
            text=part,
            reply_to_message_id=reply_to_id,
            parse_mode=ParseMode.MARKDOWN,
        )
        await asyncio.sleep(1) # Небольшая задержка, чтобы избежать rate limit


def check_user_rate_limit(db: Session, user_id: str) -> bool:
    one_hour_ago = datetime.now(UTC) - timedelta(hours=settings.user_request_limit_per_hour)
    request_count = (
        db.query(LogEntry)
        .filter(LogEntry.user_id == user_id, LogEntry.called_at >= one_hour_ago)
        .count()
    )
    return request_count < settings.user_request_limit_per_hour


def check_rate_limit(db: Session, root_post_id: str) -> bool:
    summary_record = (
        db.query(ChatSummary)
        .filter(ChatSummary.root_post_id == root_post_id)
        .first()
    )

    if summary_record and summary_record.summarized_at:
        db_time = summary_record.summarized_at
        aware_db_time = (
            db_time.replace(tzinfo=UTC) if db_time.tzinfo is None else db_time
        )

        if datetime.now(UTC) - aware_db_time < timedelta(
                hours=settings.thread_request_cooldown_hours
        ):
            return False

    return True


def update_rate_limit(db: Session, root_post_id: str):
    # ... (код функции без изменений) ...
    summary_record = (
        db.query(ChatSummary)
        .filter(ChatSummary.root_post_id == root_post_id)
        .first()
    )

    now_utc = datetime.now(UTC)

    if summary_record:
        summary_record.summarized_at = now_utc
    else:
        summary_record = ChatSummary(root_post_id=root_post_id, summarized_at=now_utc)
        db.add(summary_record)

    db.commit()


async def process_summarization_request(
    bot,
    chat_id: int,
    messages: list[dict],
    user_name: str,
    system_prompt: str,
    reply_to_message_id: int,
) -> bool:
    """Обрабатывает запрос на суммирование и отправляет результат."""
    try:
        # --- Форматирование текста для OpenAI ---
        formatted_text = ""
        for msg in messages:
            post_line = (
                f"({msg['date']}) Пользователь '{msg['user']}' написал:\n{msg['text']}\n---\n"
            )
            formatted_text += post_line

        if not formatted_text.strip():
            await bot.send_message(
                chat_id=chat_id,
                text=f"@{user_name}, не удалось найти текст в выбранных сообщениях для анализа.",
                reply_to_message_id=reply_to_message_id,
            )
            return False

        # --- Проверка стоимости запроса ---
        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            prompt_tokens = len(encoding.encode(formatted_text))
            estimated_cost = (prompt_tokens / 1000) * settings.price_per_1k_prompt

            if estimated_cost > settings.max_request_cost:
                error_message = (
                    f"@{user_name}, обработка отменена. "
                    f"Слишком много текста. Предполагаемая стоимость (${estimated_cost:.2f}) "
                    f"превышает лимит в ${settings.max_request_cost:.2f}."
                )
                await bot.send_message(
                    chat_id=chat_id,
                    text=error_message,
                    reply_to_message_id=reply_to_message_id,
                )
                return False
        except Exception as e:
            logger.exception(f"Ошибка при подсчете токенов: {e}")
            pass  # Продолжаем, даже если не удалось посчитать

        # --- Получение сводки от OpenAI ---
        summary_response = get_summary_from_openai(formatted_text, system_prompt)

        # --- Отправка результата ---
        final_message = (
            f"**Краткая сводка по запросу** @{user_name}:\n\n"
            f"{summary_response.summary}\n\n"
            f"**Стоимость запроса:** ${summary_response.cost}"
        )

        await send_message_in_chunks(
            bot, chat_id, final_message, reply_to_message_id
        )
        return True

    except TelegramError as e:
        logger.error(f"Ошибка Telegram при отправке сообщения в чат {chat_id}: {e}")
        # Попытка уведомить администратора, если чат для ошибок задан
        if settings.error_notification_chat_id:
            await bot.send_message(
                chat_id=settings.error_notification_chat_id,
                text=f"Не удалось отправить сообщение в чат {chat_id}. Ошибка: {e}"
            )
        return False
    except Exception as e:
        logger.exception(f"Критическая ошибка при обработке запроса от {user_name}")
        error_message = f"@{user_name}, произошла внутренняя ошибка. Не удалось выполнить суммирование."
        await bot.send_message(
            chat_id=chat_id, text=error_message, reply_to_message_id=reply_to_message_id
        )
        if settings.error_notification_chat_id:
            await bot.send_message(
                chat_id=settings.error_notification_chat_id,
                text=f"Критическая ошибка в боте при запросе от @{user_name} в чате {chat_id}:\n\n{e}",
            )
        return False