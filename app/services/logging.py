from sqlalchemy.orm import Session

from app.models import LogEntry


def log_summary_request(db: Session, user_id: str, root_post_id: str):
    log_entry = LogEntry(user_id=user_id, root_post_id=root_post_id)
    db.add(log_entry)
    db.commit()
