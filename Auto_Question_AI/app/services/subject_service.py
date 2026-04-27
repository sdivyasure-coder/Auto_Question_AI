from sqlalchemy.orm import Session

from app.models.subject import Subject


def create_subject(db: Session, code: str, name: str, description: str | None = None) -> Subject:
    subject = Subject(code=code, name=name, description=description)
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject


def get_subject(db: Session, subject_id: int) -> Subject | None:
    return db.query(Subject).filter(Subject.id == subject_id).first()


def get_subject_by_code(db: Session, code: str) -> Subject | None:
    return db.query(Subject).filter(Subject.code == code).first()


def list_subjects(db: Session):
    return db.query(Subject).order_by(Subject.id).all()


def update_subject(db: Session, subject: Subject, name: str | None = None, description: str | None = None) -> Subject:
    if name is not None:
        subject.name = name
    if description is not None:
        subject.description = description
    db.commit()
    db.refresh(subject)
    return subject


def delete_subject(db: Session, subject: Subject) -> None:
    db.delete(subject)
    db.commit()
