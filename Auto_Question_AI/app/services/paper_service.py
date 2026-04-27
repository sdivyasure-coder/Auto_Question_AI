import os
from datetime import datetime
from typing import Dict, List

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.ai_engine.generator import generate_question_paper
from app.models.paper import Paper
from app.models.paper_question import PaperQuestion
from app.models.subject import Subject


OUTPUT_DIR = "output/papers"


def _ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def create_paper_record(
    db: Session,
    subject: Subject,
    user_id: int | None,
    difficulty: str,
    pattern: str,
    max_marks: int,
    questions: List[Dict],
) -> Paper:
    title = f"{subject.code} Question Paper {datetime.now().strftime('%Y%m%d_%H%M%S')}"
    paper = Paper(
        subject_id=subject.id,
        user_id=user_id,
        title=title,
        pattern=pattern,
        max_marks=max_marks,
        difficulty=difficulty,
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)

    links = [
        PaperQuestion(
            paper_id=paper.id,
            question_id=q["id"],
            display_marks=q.get("display_marks"),
        )
        for q in questions
    ]
    db.add_all(links)
    db.commit()

    return paper


def generate_pdf(paper: Paper, subject: Subject, questions: List[Dict]) -> str:
    _ensure_output_dir()
    filename = f"paper_{paper.id}.pdf"
    file_path = os.path.join(OUTPUT_DIR, filename)

    c = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter
    y = height - 0.75 * inch

    def draw_line(text: str, font="Times-Roman", size=11, leading=14):
        nonlocal y
        if y < 1 * inch:
            c.showPage()
            y = height - 0.75 * inch
        c.setFont(font, size)
        c.drawString(0.75 * inch, y, text)
        y -= leading

    draw_line(f"AI Question Paper | {subject.name}", font="Times-Bold", size=12)
    draw_line(f"Pattern: {paper.pattern} | Max Marks: {paper.max_marks}", size=10)
    draw_line(f"Generated: {paper.created_at}", size=9)
    y -= 8

    for idx, q in enumerate(questions, start=1):
        marks = q.get("display_marks") or str(q.get("mark", ""))
        draw_line(f"{idx}. {q['text']} ({marks} Marks)")

    c.save()
    return file_path


def generate_and_store_paper(
    db: Session,
    subject: Subject,
    user_id: int | None,
    marks: int,
    difficulty: str,
) -> Paper:
    payload = generate_question_paper(db, subject.id, marks, difficulty)
    paper = create_paper_record(
        db,
        subject,
        user_id,
        difficulty,
        payload["pattern"],
        payload["max_marks"],
        payload["questions"],
    )
    file_path = generate_pdf(paper, subject, payload["questions"])
    paper.file_path = file_path
    db.commit()
    db.refresh(paper)
    return paper
