from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.schemas.subject import SubjectCreate, SubjectUpdate, SubjectOut
from app.services.subject_service import create_subject, get_subject, get_subject_by_code, list_subjects, update_subject, delete_subject
from app.utils.deps import get_db, require_roles
from app.utils.response import success_response

router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.get("/")
def get_all(db: Session = Depends(get_db)):
    subjects = list_subjects(db)
    data = [SubjectOut.model_validate(s).model_dump() for s in subjects]
    return success_response(data)


@router.post("/")
def create(payload: SubjectCreate, db: Session = Depends(get_db), _=Depends(require_roles("admin", "staff"))):
    if get_subject_by_code(db, payload.code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subject code already exists")
    subject = create_subject(db, payload.code, payload.name, payload.description)
    return success_response(SubjectOut.model_validate(subject).model_dump(), "Subject created")


@router.put("/{subject_id}")
def update(subject_id: int, payload: SubjectUpdate, db: Session = Depends(get_db), _=Depends(require_roles("admin", "staff"))):
    subject = get_subject(db, subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    subject = update_subject(db, subject, payload.name, payload.description)
    return success_response(SubjectOut.model_validate(subject).model_dump(), "Subject updated")


@router.delete("/{subject_id}")
def remove(subject_id: int, db: Session = Depends(get_db), _=Depends(require_roles("admin", "staff"))):
    subject = get_subject(db, subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    delete_subject(db, subject)
    return success_response({}, "Subject deleted")
