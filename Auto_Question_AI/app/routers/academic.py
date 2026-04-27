from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.models.generated_paper import GeneratedPaper
from app.models.subject import Subject
from app.models.unit import Unit
from app.schemas.academic import (
    AnalyticsOut,
    CollegeBrandingIn,
    ImproveQuestionIn,
    ImproveQuestionOut,
    PaperGenerateV2In,
    PaperV2Out,
    SectionEditIn,
    ThemeSettingIn,
    UnitIn,
    UnitOut,
    UploadExtractOut,
    WeightageOut,
)
from app.services.academic_service import (
    analytics_dashboard,
    export_paper_files,
    extract_questions_from_upload,
    generate_paper_v2,
    get_setting,
    history_search,
    improve_question_text,
    paper_to_dict,
    regenerate_section,
    save_draft,
    save_setting,
    save_upload_file,
    seed_default_templates,
    shuffle_questions,
    unit_weightage,
)
from app.utils.deps import get_current_user, get_db
from app.utils.response import success_response

router = APIRouter(prefix="/academic", tags=["academic"])


@router.post("/templates/seed")
def seed_templates(db: Session = Depends(get_db), _=Depends(get_current_user)):
    seed_default_templates(db)
    return success_response({}, "Templates seeded")


@router.get("/units")
def list_units(subject_id: Optional[int] = None, db: Session = Depends(get_db), _=Depends(get_current_user)):
    query = db.query(Unit)
    if subject_id:
        query = query.filter(Unit.subject_id == subject_id)
    data = [UnitOut.model_validate(row).model_dump() for row in query.order_by(Unit.subject_id, Unit.unit_no).all()]
    return success_response(data)


@router.post("/units")
def create_unit(payload: UnitIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    subject = db.query(Subject).filter(Subject.id == payload.subject_id).first()
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")

    existing = (
        db.query(Unit)
        .filter(Unit.subject_id == payload.subject_id, Unit.unit_no == payload.unit_no)
        .first()
    )
    if existing:
        existing.title = payload.title
        existing.weightage_percent = payload.weightage_percent
        db.commit()
        db.refresh(existing)
        return success_response(UnitOut.model_validate(existing).model_dump(), "Unit updated")

    row = Unit(
        subject_id=payload.subject_id,
        unit_no=payload.unit_no,
        title=payload.title,
        weightage_percent=payload.weightage_percent,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return success_response(UnitOut.model_validate(row).model_dump(), "Unit created")


@router.post("/papers/generate")
def generate_paper(payload: PaperGenerateV2In, db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        paper = generate_paper_v2(
            db,
            user.id,
            payload.subject_id,
            payload.unit_ids,
            payload.total_marks,
            payload.difficulty,
            payload.question_count,
            payload.template_name,
            payload.exam_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    data = PaperV2Out(**paper_to_dict(paper)).model_dump()
    return success_response(data, "Paper generated")


@router.get("/papers/history")
def paper_history(
    subject_id: Optional[int] = None,
    q: str = "",
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    papers = history_search(db, user.id, subject_id=subject_id, query=q)
    data = [
        {
            "id": row.id,
            "title": row.title,
            "subject_id": row.subject_id,
            "total_marks": row.total_marks,
            "requested_difficulty": row.requested_difficulty,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
        for row in papers
    ]
    return success_response(data)


@router.get("/papers/{paper_id}")
def get_paper(paper_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    paper = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id, GeneratedPaper.user_id == user.id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return success_response(PaperV2Out(**paper_to_dict(paper)).model_dump())


@router.post("/papers/{paper_id}/regenerate")
def regenerate_paper(paper_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    paper = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id, GeneratedPaper.user_id == user.id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")

    unit_ids = []
    data = paper.selected_units_json
    if data:
        try:
            unit_nos = [int(v) for v in __import__("json").loads(data)]
            unit_ids = [u.id for u in db.query(Unit).filter(Unit.subject_id == paper.subject_id, Unit.unit_no.in_(unit_nos)).all()]
        except Exception:
            unit_ids = []

    regenerated = generate_paper_v2(
        db,
        user.id,
        paper.subject_id,
        unit_ids,
        paper.total_marks,
        paper.requested_difficulty,
        paper.num_questions,
        paper.template.name if paper.template else "semester",
        paper.exam_date,
    )
    return success_response(PaperV2Out(**paper_to_dict(regenerated)).model_dump(), "Paper regenerated")


@router.post("/papers/{paper_id}/regenerate-section")
def regenerate_paper_section(paper_id: int, payload: SectionEditIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    paper = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id, GeneratedPaper.user_id == user.id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")

    regenerated = regenerate_section(db, paper_id, payload.section)
    return success_response(PaperV2Out(**paper_to_dict(regenerated)).model_dump(), "Section regenerated")


@router.post("/papers/{paper_id}/shuffle")
def shuffle_paper(paper_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    paper = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id, GeneratedPaper.user_id == user.id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    out = shuffle_questions(db, paper_id)
    return success_response(PaperV2Out(**paper_to_dict(out)).model_dump(), "Questions shuffled")


@router.post("/papers/{paper_id}/save-draft")
def save_paper_draft(paper_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    paper = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id, GeneratedPaper.user_id == user.id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    out = save_draft(db, paper_id)
    return success_response(PaperV2Out(**paper_to_dict(out)).model_dump(), "Draft saved")


@router.post("/papers/{paper_id}/quality-check")
def paper_quality(paper_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    paper = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id, GeneratedPaper.user_id == user.id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return success_response(PaperV2Out(**paper_to_dict(paper)).model_dump().get("quality_report", {}), "Quality report")


@router.post("/papers/{paper_id}/answer-key")
def paper_answer_key(paper_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    paper = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id, GeneratedPaper.user_id == user.id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return success_response(PaperV2Out(**paper_to_dict(paper)).model_dump().get("answer_keys", {}), "Answer key generated")


@router.get("/papers/{paper_id}/preview-html")
def preview_html(paper_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    paper = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id, GeneratedPaper.user_id == user.id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return success_response({"preview_html": paper.preview_html})


@router.post("/papers/{paper_id}/export")
def export(paper_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    paper = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id, GeneratedPaper.user_id == user.id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    out = export_paper_files(db, paper_id)
    return success_response(PaperV2Out(**paper_to_dict(out)).model_dump(), "Exported PDF and DOCX")


@router.post("/question-bank/upload/{file_type}")
async def upload_question_source(
    file_type: str,
    subject_id: Optional[int] = None,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if file_type not in ["syllabus", "prev_year"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file type")

    content = await file.read()
    upload = save_upload_file(db, user.id, subject_id, file_type, file.filename or "upload.txt", content)
    return success_response({"upload_id": upload.id, "file_path": upload.file_path}, "File uploaded")


@router.post("/question-bank/extract/{upload_id}")
def extract_questions(upload_id: int, subject_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    try:
        inserted_count, parse_status = extract_questions_from_upload(db, upload_id, subject_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    data = UploadExtractOut(upload_id=upload_id, inserted_count=inserted_count, parse_status=parse_status).model_dump()
    return success_response(data, "Questions extracted")


@router.post("/question-bank/improve")
def improve_question(payload: ImproveQuestionIn, _=Depends(get_current_user)):
    improved = improve_question_text(payload.question_text)
    return success_response(ImproveQuestionOut(improved_text=improved).model_dump(), "Question improved")


@router.get("/papers/{paper_id}/weightage", response_model=None)
def weightage(paper_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    paper = db.query(GeneratedPaper).filter(GeneratedPaper.id == paper_id, GeneratedPaper.user_id == user.id).first()
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    data = unit_weightage(db, paper_id)
    return success_response(WeightageOut(**data).model_dump())


@router.get("/analytics/dashboard")
def analytics(db: Session = Depends(get_db), _=Depends(get_current_user)):
    data = analytics_dashboard(db)
    return success_response(AnalyticsOut(**data).model_dump())


@router.post("/settings/theme")
def set_theme(payload: ThemeSettingIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    setting = save_setting(db, "theme", {"theme": payload.theme})
    return success_response({"key": setting.key, "value": payload.theme}, "Theme saved")


@router.get("/settings/theme")
def get_theme(db: Session = Depends(get_db), _=Depends(get_current_user)):
    data = get_setting(db, "theme", {"theme": "dark"})
    return success_response(data)


@router.post("/settings/college-branding")
def college_branding(payload: CollegeBrandingIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    setting = save_setting(db, "college_branding", payload.model_dump())
    return success_response({"key": setting.key, "value": payload.model_dump()}, "Branding saved")


@router.get("/settings/college-branding")
def get_college_branding(db: Session = Depends(get_db), _=Depends(get_current_user)):
    data = get_setting(db, "college_branding", {"college_name": "", "subject_code_prefix": "", "exam_date_format": "DD-MM-YYYY", "logo_path": None})
    return success_response(data)
