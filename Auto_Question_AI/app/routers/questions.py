from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.schemas.question import QuestionCreate, QuestionUpdate, QuestionOut
from app.services.question_service import create_question, get_question, list_questions, update_question, delete_question, bulk_create_questions
from app.services.subject_service import get_subject
from app.models.question import Question
from app.utils.deps import get_db, require_roles
from app.utils.response import success_response

router = APIRouter(prefix="/questions", tags=["questions"])


@router.get("/")
def get_all(subject_id: int | None = None, db: Session = Depends(get_db)):
    questions = list_questions(db, subject_id)
    data = [QuestionOut.model_validate(q).model_dump() for q in questions]
    return success_response(data)


@router.post("/")
def create(payload: QuestionCreate, db: Session = Depends(get_db), _=Depends(require_roles("admin", "staff"))):
    subject = get_subject(db, payload.subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    question = create_question(
        db,
        payload.subject_id,
        payload.chapter,
        payload.text,
        payload.mark,
        payload.difficulty,
        payload.source or "bank",
    )
    return success_response(QuestionOut.model_validate(question).model_dump(), "Question created")


@router.put("/{question_id}")
def update(question_id: int, payload: QuestionUpdate, db: Session = Depends(get_db), _=Depends(require_roles("admin", "staff"))):
    question = get_question(db, question_id)
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    question = update_question(db, question, **payload.model_dump(exclude_unset=True))
    return success_response(QuestionOut.model_validate(question).model_dump(), "Question updated")


@router.delete("/{question_id}")
def remove(question_id: int, db: Session = Depends(get_db), _=Depends(require_roles("admin", "staff"))):
    question = get_question(db, question_id)
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    delete_question(db, question)
    return success_response({}, "Question deleted")


@router.post("/bulk")
def bulk_upload(payload: list[QuestionCreate], db: Session = Depends(get_db), _=Depends(require_roles("admin", "staff"))):
    items: list[Question] = []
    for row in payload:
        subject = get_subject(db, row.subject_id)
        if not subject:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Subject not found: {row.subject_id}")
        items.append(
            Question(
                subject_id=row.subject_id,
                chapter=row.chapter,
                text=row.text,
                mark=row.mark,
                difficulty=row.difficulty,
                source=row.source or "bank",
            )
        )
    created = bulk_create_questions(db, items)
    data = [QuestionOut.model_validate(q).model_dump() for q in created]
    return success_response(data, "Bulk upload successful")
