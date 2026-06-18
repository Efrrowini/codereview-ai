import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from backend.models import get_db, Submission
from core.reviewer import CodeReviewer
from core.rubric import Rubric, BUILTIN_RUBRICS

router = APIRouter()


# --- Request / Response schemas ---

class ReviewRequest(BaseModel):
    code: str
    assignment_prompt: str
    language: str = "python"
    rubric_name: Optional[str] = None    # use a built-in rubric by name
    rubric_json: Optional[str] = None    # or pass a custom rubric as JSON
    assignment_title: Optional[str] = "Untitled Assignment"


class ReviewResponse(BaseModel):
    submission_id: int
    overall_score: float
    grade_letter: str
    summary: str
    criteria_scores: list[dict]
    line_comments: list[dict]
    strengths: list[str]
    improvements: list[str]
    static_analysis: dict


# --- Routes ---

@router.post("/review", response_model=ReviewResponse)
def review_code(req: ReviewRequest, db: Session = Depends(get_db)):
    # Resolve rubric
    if req.rubric_json:
        try:
            rubric = Rubric.from_json(req.rubric_json)
        except Exception as e:
            raise HTTPException(400, f"Invalid rubric JSON: {e}")
    elif req.rubric_name:
        rubric = BUILTIN_RUBRICS.get(req.rubric_name)
        if not rubric:
            raise HTTPException(404, f"Rubric '{req.rubric_name}' not found")
    else:
        rubric = None   # reviewer will use default

    # Run review
    try:
        reviewer = CodeReviewer()
    except ValueError as e:
        raise HTTPException(500, str(e))

    result = reviewer.review(
        code=req.code,
        assignment_prompt=req.assignment_prompt,
        rubric=rubric,
        language=req.language,
    )

    if not result.success:
        raise HTTPException(500, result.error)

    # Save to DB
    submission = Submission(
        assignment_title=req.assignment_title,
        language=req.language,
        code=req.code,
        assignment_prompt=req.assignment_prompt,
        rubric_json=rubric.to_json() if rubric else None,
        feedback_json=json.dumps(result.raw_json),
        overall_score=result.overall_score,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    return ReviewResponse(
        submission_id=submission.id,
        overall_score=result.overall_score,
        grade_letter=result.grade_letter,
        summary=result.summary,
        criteria_scores=[
            {
                "name": cs.name,
                "score": cs.score,
                "weight": cs.weight,
                "weighted_score": cs.weighted_score,
                "feedback": cs.feedback,
            }
            for cs in result.criteria_scores
        ],
        line_comments=[
            {"line": lc.line, "type": lc.type, "comment": lc.comment}
            for lc in result.line_comments
        ],
        strengths=result.strengths,
        improvements=result.improvements,
        static_analysis=result.static_analysis.to_dict() if result.static_analysis else {},
    )


@router.get("/rubrics")
def list_rubrics():
    return {
        "builtin": [
            {"name": name, "criteria": [c.name for c in r.criteria]}
            for name, r in BUILTIN_RUBRICS.items()
        ]
    }


@router.get("/submissions")
def list_submissions(limit: int = 20, db: Session = Depends(get_db)):
    subs = db.query(Submission).order_by(Submission.submitted_at.desc()).limit(limit).all()
    return [
        {
            "id": s.id,
            "assignment_title": s.assignment_title,
            "language": s.language,
            "overall_score": s.overall_score,
            "submitted_at": s.submitted_at.isoformat(),
        }
        for s in subs
    ]


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: int, db: Session = Depends(get_db)):
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if not sub:
        raise HTTPException(404, "Submission not found")
    return {
        "id": sub.id,
        "assignment_title": sub.assignment_title,
        "language": sub.language,
        "code": sub.code,
        "assignment_prompt": sub.assignment_prompt,
        "feedback": json.loads(sub.feedback_json) if sub.feedback_json else {},
        "overall_score": sub.overall_score,
        "submitted_at": sub.submitted_at.isoformat(),
    }
