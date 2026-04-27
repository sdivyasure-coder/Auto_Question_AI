from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.schemas.paper import PaperGenerate, PaperOut, PaperHistoryOut
from app.services.paper_service import generate_and_store_paper
from app.services.subject_service import get_subject
from app.models.paper import Paper
from app.utils.deps import get_db, get_current_user
from app.utils.response import success_response

router = APIRouter(prefix="/paper", tags=["paper"])


@router.post("/generate")
def generate(payload: PaperGenerate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    subject = get_subject(db, payload.subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")

    paper = generate_and_store_paper(db, subject, user.id, payload.marks, payload.difficulty)
    data = PaperOut.model_validate(paper).model_dump()
    if paper.file_path:
        rel_path = paper.file_path.replace("output\\", "").replace("output/", "").replace("\\", "/")
        data["download_url"] = f"/files/{rel_path}"
    else:
        data["download_url"] = None
    return success_response(data, "Paper generated")


@router.get("/history")
def history(db: Session = Depends(get_db), user=Depends(get_current_user)):
    papers = db.query(Paper).filter(Paper.user_id == user.id).order_by(Paper.id.desc()).all()
    data = [PaperHistoryOut.model_validate(p).model_dump() for p in papers]
    return success_response(data)


@router.get("/download/{paper_id}")
def download(paper_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    paper = db.query(Paper).filter(Paper.id == paper_id, Paper.user_id == user.id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    if not paper.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    rel_path = paper.file_path.replace("output\\", "").replace("output/", "").replace("\\", "/")
    data = {
        "paper_id": paper.id,
        "file_path": paper.file_path,
        "download_url": f"/files/{rel_path}",
    }
    return success_response(data, "Download link")
