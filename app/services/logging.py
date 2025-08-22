from sqlalchemy.orm import Session

from app.models import LogEntry


def log_summary_request(db: Session, user_name: str, root_post_id: str):
    log_entry = LogEntry(user_name=user_name, root_post_id=root_post_id)
    db.add(log_entry)
    db.commit()
