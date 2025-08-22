import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.database import engine, Base
from app.endpoints import router
from app.security import BasicAuthBackend, on_auth_error
from telegram_bot import run_bot

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Запуск FastAPI приложения...")
    Base.metadata.create_all(bind=engine)

    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("Telegram-бот запущен в фоновом режиме...")

    yield

    logger.info("Остановка FastAPI приложения...")


app = FastAPI(lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key="a-very-secret-key")
app.add_middleware(
    AuthenticationMiddleware, backend=BasicAuthBackend(), on_error=on_auth_error
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
