from typing import List
from sqlalchemy.orm import Session

from app.models.question import Question


def create_question(
    db: Session,
    subject_id: int,
    chapter: int,
    text: str,
    mark: int,
    difficulty: str,
    source: str = "bank",
) -> Question:
    question = Question(
        subject_id=subject_id,
        chapter=chapter,
        text=text,
        mark=mark,
        difficulty=difficulty,
        source=source,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


def get_question(db: Session, question_id: int) -> Question | None:
    return db.query(Question).filter(Question.id == question_id).first()


def list_questions(db: Session, subject_id: int | None = None):
    query = db.query(Question)
    if subject_id is not None:
        query = query.filter(Question.subject_id == subject_id)
    return query.order_by(Question.id.desc()).all()


def update_question(db: Session, question: Question, **kwargs) -> Question:
    for key, value in kwargs.items():
        if value is not None:
            setattr(question, key, value)
    db.commit()
    db.refresh(question)
    return question


def delete_question(db: Session, question: Question) -> None:
    db.delete(question)
    db.commit()


def bulk_create_questions(db: Session, items: List[Question]) -> List[Question]:
    db.add_all(items)
    db.commit()
    for item in items:
        db.refresh(item)
    return items
