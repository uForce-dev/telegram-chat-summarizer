import logging
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def parse_message_link(link: str) -> dict[str, Any] | None:
    """Парсит ссылку на сообщение в Telegram."""
    try:
        parsed = urlparse(link)
        if parsed.netloc != "t.me":
            return None

        parts = parsed.path.strip("/").split("/")
        if len(parts) == 2:
            # Ссылка на публичный канал
            chat_id = "@" + parts[0]
            message_id = int(parts[1])
        elif len(parts) == 3 and parts[0] == "c":
            # Ссылка на приватный канал/группу
            chat_id = int("-100" + parts[1])
            message_id = int(parts[2])
        else:
            return None

        return {"chat_id": chat_id, "message_id": message_id}
    except (ValueError, IndexError):
        return None


async def get_thread_messages(bot, chat_id, message_id) -> list[dict]:
    """
    В Telegram нет явного понятия "треда" как в Mattermost.
    Будем считать "тредом" все ответы на указанное сообщение.
    К сожалению, стандартный Bot API не позволяет легко получить все ответы на сообщение.
    Поэтому в данной реализации мы будем суммировать только само сообщение.
    Для полноценной работы с тредами (темами в группах) потребуется более сложная логика
    и, возможно, использование User API (что не рекомендуется для ботов).

    В качестве упрощения, мы будем запрашивать само сообщение.
    """
    try:
        message = await bot.forward_message(
            chat_id=chat_id, from_chat_id=chat_id, message_id=message_id
        )
        await bot.delete_message(chat_id=chat_id, message_id=message.message_id)

        user = message.forward_from or message.author_signature
        username = ""
        if user:
            username = (
                user.username or user.first_name or getattr(user, "title", "Unknown")
            )

        return [
            {
                "user": username,
                "text": message.text or message.caption or "",
                "date": message.date,
            }
        ]
    except Exception as e:
        logger.error(f"Не удалось получить сообщение: {e}")
        return []
