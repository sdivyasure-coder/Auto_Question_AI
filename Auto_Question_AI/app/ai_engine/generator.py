from typing import Dict, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.models.question import Question


def _difficulty_ratio(difficulty: str) -> Tuple[float, float, float]:
    difficulty = difficulty.lower()
    if difficulty == "easy":
        return 0.6, 0.3, 0.1
    if difficulty == "hard":
        return 0.2, 0.3, 0.5
    if difficulty == "medium":
        return 0.3, 0.5, 0.2
    return 0.34, 0.33, 0.33


def _pattern_for_marks(marks: int) -> Dict:
    if marks == 75:
        return {
            "pattern": "75",
            "max_marks": 75,
            "buckets": [
                {"mark": 2, "count": 10, "display": 2},
                {"mark": 7, "count": 5, "display": 5},
                {"mark": 15, "count": 3, "display": 10},
            ],
        }
    if marks == 50:
        return {
            "pattern": "50",
            "max_marks": 50,
            "buckets": [
                {"mark": 2, "count": 6, "display": 2},
                {"mark": 7, "count": 3, "display": 6},
                {"mark": 15, "count": 2, "display": 10},
            ],
        }
    return {
        "pattern": "100",
        "max_marks": 100,
        "buckets": [
            {"mark": 2, "count": 10, "display": 2},
            {"mark": 7, "count": 5, "display": 7},
            {"mark": 15, "count": 3, "display": 15},
        ],
    }


def _pick_questions(
    db: Session,
    subject_id: int,
    mark: int,
    count: int,
    difficulty: str,
    used_ids: set,
) -> List[Question]:
    query = db.query(Question).filter(
        Question.subject_id == subject_id,
        Question.mark == mark,
        Question.active.is_(True),
    )

    if difficulty != "balanced":
        query = query.filter(Question.difficulty == difficulty)

    results = query.order_by(func.random()).limit(count).all()
    if len(results) < count:
        fallback = (
            db.query(Question)
            .filter(
                Question.subject_id == subject_id,
                Question.mark == mark,
                Question.active.is_(True),
            )
            .order_by(func.random())
            .limit(count * 2)
            .all()
        )
        for item in fallback:
            if item.id in used_ids:
                continue
            results.append(item)
            if len(results) >= count:
                break

    selected = []
    for item in results:
        if item.id in used_ids:
            continue
        selected.append(item)
        used_ids.add(item.id)
        if len(selected) >= count:
            break
    return selected


def generate_question_paper(db: Session, subject_id: int, marks: int, difficulty: str) -> Dict:
    difficulty = difficulty.lower()
    pattern = _pattern_for_marks(marks)
    used_ids = set()

    easy_ratio, med_ratio, hard_ratio = _difficulty_ratio(difficulty)
    questions_out = []

    for bucket in pattern["buckets"]:
        count = bucket["count"]
        easy_count = max(0, int(count * easy_ratio))
        med_count = max(0, int(count * med_ratio))
        hard_count = max(0, count - easy_count - med_count)

        selected = []
        selected.extend(_pick_questions(db, subject_id, bucket["mark"], easy_count, "easy", used_ids))
        selected.extend(_pick_questions(db, subject_id, bucket["mark"], med_count, "medium", used_ids))
        selected.extend(_pick_questions(db, subject_id, bucket["mark"], hard_count, "hard", used_ids))

        if len(selected) < count:
            extra = _pick_questions(db, subject_id, bucket["mark"], count - len(selected), "balanced", used_ids)
            selected.extend(extra)

        for q in selected:
            questions_out.append(
                {
                    "id": q.id,
                    "text": q.text,
                    "mark": q.mark,
                    "display_marks": str(bucket["display"]),
                }
            )

    return {
        "pattern": pattern["pattern"],
        "max_marks": pattern["max_marks"],
        "questions": questions_out,
    }
