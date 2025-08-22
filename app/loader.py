from fastapi.templating import Jinja2Templates

from app.config import Settings

settings = Settings()
templates = Jinja2Templates(directory=settings.TEMPLATES_PATH)
