from sqlalchemy import Column, Integer, String, DateTime, func, Text

from app.database import Base


class ChatSummary(Base):
    __tablename__ = "tg_chats_summaries"

    id = Column(Integer, primary_key=True, index=True)
    root_post_id = Column(String, unique=True, index=True)
    summarized_at = Column(DateTime(timezone=True), server_default=func.now())


class Prompt(Base):
    __tablename__ = "tg_chats_prompts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    text = Column(Text, nullable=False)


class LogEntry(Base):
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    root_post_id = Column(String, index=True)
    called_at = Column(DateTime(timezone=True), server_default=func.now())
