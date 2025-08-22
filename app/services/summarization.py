import logging
from datetime import datetime, UTC, timedelta

import tiktoken
from sqlalchemy.orm import Session

from app.loader import settings
from app.models import ChatSummary, LogEntry
from app.services.openai import get_summary_from_openai

logger = logging.getLogger(__name__)


def check_user_rate_limit(db: Session, user_name: str) -> bool:
    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    request_count = (
        db.query(LogEntry)
        .filter(LogEntry.user_name == user_name, LogEntry.called_at >= one_hour_ago)
        .count()
    )
    return request_count < settings.USER_REQUEST_LIMIT_PER_HOUR


def check_rate_limit(db: Session, root_post_id: str) -> bool:
    summary_record = (
        db.query(ChatSummary).filter(ChatSummary.root_post_id == root_post_id).first()
    )

    if summary_record and summary_record.summarized_at:
        db_time = summary_record.summarized_at
        aware_db_time = (
            db_time.replace(tzinfo=UTC) if db_time.tzinfo is None else db_time
        )

        if datetime.now(UTC) - aware_db_time < timedelta(
            hours=settings.THREAD_REQUEST_COOLDOWN_HOURS
        ):
            return False

    return True


def update_rate_limit(db: Session, root_post_id: str):
    summary_record = (
        db.query(ChatSummary).filter(ChatSummary.root_post_id == root_post_id).first()
    )

    now_utc = datetime.now(UTC)

    if summary_record:
        summary_record.summarized_at = now_utc
    else:
        summary_record = ChatSummary(root_post_id=root_post_id, summarized_at=now_utc)
        db.add(summary_record)

    db.commit()


def process_summarization_request(
    bot,
    chat_id: int,
    thread_messages: list[dict],
    user_name: str,
    system_prompt: str,
    reply_to_message_id: int,
) -> bool:
    try:
        formatted_text = ""
        for msg in thread_messages:
            post_line = f"({msg['date']}) Пользователь '{msg['user']}' написал:\n{msg['text']}\n---\n"
            formatted_text += post_line

        if not formatted_text:
            bot.send_message(
                chat_id=chat_id,
                text=f"@{user_name}, не удалось обработать, так как нет текста для анализа.",
                reply_to_message_id=reply_to_message_id,
            )
            return False

        try:
            encoding = tiktoken.get_encoding("cl100k_base")
            prompt_tokens = len(encoding.encode(formatted_text))
            estimated_cost = (prompt_tokens / 1000) * settings.price_per_1k_prompt

            if estimated_cost > settings.MAX_REQUEST_COST:
                error_message = (
                    f"@{user_name}, обработка отменена. "
                    f"Предполагаемая стоимость запроса (${estimated_cost:.2f}) "
                    f"превышает лимит в ${settings.MAX_REQUEST_COST:.2f}."
                )
                bot.send_message(
                    chat_id=chat_id,
                    text=error_message,
                    reply_to_message_id=reply_to_message_id,
                )
                return False
        except Exception as e:
            logger.exception(f"Ошибка при подсчете токенов: {e}")
            pass

        summary_response = get_summary_from_openai(formatted_text, system_prompt)

        final_message = (
            f"**Краткая сводка по запросу** @{user_name}:\n\n"
            f"{summary_response.summary}\n\n"
            f"**Стоимость запроса:** ${summary_response.cost}"
        )
        bot.send_message(
            chat_id=chat_id,
            text=final_message,
            reply_to_message_id=reply_to_message_id,
        )
        return True

    except Exception as e:
        logger.exception(f"Произошла ошибка при обработке запроса от {user_name}")
        error_message = f"@{user_name}, не удалось выполнить саммаризацию. Произошла внутренняя ошибка."
        bot.send_message(
            chat_id=chat_id,
            text=error_message,
            reply_to_message_id=reply_to_message_id,
        )

        # Отправка уведомления об ошибке администратору
        admin_chat_id = settings.error_notification_channel_id
        if admin_chat_id:
            admin_error_message = (
                f"Ошибка в боте-саммаризаторе:\n"
                f"Пользователь: @{user_name}\n"
                f"Ошибка: {e}"
            )
            bot.send_message(chat_id=admin_chat_id, text=admin_error_message)

        return False
