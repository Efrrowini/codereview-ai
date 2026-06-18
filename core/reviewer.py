import json
import os
from dataclasses import dataclass, field
from typing import Optional

from groq import Groq
from dotenv import load_dotenv

from core.analyzer import analyze, AnalysisResult
from core.prompt_builder import SYSTEM_PROMPT, build_review_prompt
from core.rubric import Rubric, DEFAULT_PYTHON_RUBRIC

load_dotenv()


@dataclass
class LineComment:
    line: int
    type: str
    comment: str


@dataclass
class CriterionScore:
    name: str
    score: float
    weight: float
    weighted_score: float
    feedback: str


@dataclass
class ReviewResult:
    overall_score: float
    grade_letter: str
    summary: str
    criteria_scores: list[CriterionScore] = field(default_factory=list)
    line_comments: list[LineComment] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    static_analysis: Optional[AnalysisResult] = None
    raw_json: Optional[dict] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


class CodeReviewer:
    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("GROQ_API_KEY")
        if not key:
            raise ValueError("GROQ_API_KEY not set")
        self.client = Groq(api_key=key)

    def review(
        self,
        code: str,
        assignment_prompt: str,
        rubric: Optional[Rubric] = None,
        language: str = "python",
    ) -> ReviewResult:

        if rubric is None:
            rubric = DEFAULT_PYTHON_RUBRIC

        analysis = analyze(code, language)

        user_message = build_review_prompt(
            code=code,
            assignment_prompt=assignment_prompt,
            rubric=rubric,
            analysis=analysis,
            language=language,
        )

        try:
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
            raw_text = response.choices[0].message.content.strip()

            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            raw_text = raw_text.strip()

            data = json.loads(raw_text)

        except json.JSONDecodeError as e:
            return ReviewResult(
                overall_score=0, grade_letter="F", summary="",
                error=f"Failed to parse response as JSON: {e}",
            )
        except Exception as e:
            return ReviewResult(
                overall_score=0, grade_letter="F", summary="",
                error=f"Groq API error: {e}",
            )

        criteria_scores = [CriterionScore(**cs) for cs in data.get("criteria_scores", [])]
        line_comments = [LineComment(**lc) for lc in data.get("line_comments", [])]

        return ReviewResult(
            overall_score=data.get("overall_score", 0),
            grade_letter=data.get("grade_letter", "?"),
            summary=data.get("summary", ""),
            criteria_scores=criteria_scores,
            line_comments=line_comments,
            strengths=data.get("strengths", []),
            improvements=data.get("improvements", []),
            static_analysis=analysis,
            raw_json=data,
        )