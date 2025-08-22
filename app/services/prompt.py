from sqlalchemy.orm import Session

from app.models import Prompt


def get_all_prompts(db: Session):
    return db.query(Prompt).all()


def create_prompt(db: Session, name: str, text: str):
    db_prompt = Prompt(name=name, text=text)
    db.add(db_prompt)
    db.commit()
    db.refresh(db_prompt)
    return db_prompt


def get_prompt_by_name(db: Session, name: str):
    return db.query(Prompt).filter(Prompt.name == name).first()


def get_prompt_by_id(db: Session, prompt_id: int):
    return db.query(Prompt).filter(Prompt.id == prompt_id).first()


def update_prompt(db: Session, prompt_id: int, name: str, text: str):
    db_prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    if db_prompt:
        db_prompt.name = name
        db_prompt.text = text
        db.commit()
        db.refresh(db_prompt)
    return db_prompt


def delete_prompt(db: Session, prompt_id: int):
    db_prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    if db_prompt:
        db.delete(db_prompt)
        db.commit()
