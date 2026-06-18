"""
Builds the structured prompt sent to Claude.
Combines: assignment context + rubric + static analysis + student code.
"""
from core.rubric import Rubric
from core.analyzer import AnalysisResult


SYSTEM_PROMPT = """You are CodeReview AI, an expert CS teaching assistant that reviews student code submissions.

Your job is to give structured, constructive feedback exactly as a senior CS educator would — specific, actionable, and encouraging.

You MUST respond with valid JSON only. No markdown, no explanation outside the JSON.

Response format:
{
  "overall_score": <float 0-100>,
  "summary": "<2-3 sentence overall assessment>",
  "criteria_scores": [
    {
      "name": "<criterion name>",
      "score": <float 0-10>,
      "weight": <float>,
      "weighted_score": <float>,
      "feedback": "<specific feedback for this criterion>"
    }
  ],
  "line_comments": [
    {
      "line": <int>,
      "type": "error|warning|suggestion|praise",
      "comment": "<specific comment about this line>"
    }
  ],
  "strengths": ["<strength 1>", "<strength 2>"],
  "improvements": ["<improvement 1>", "<improvement 2>", "<improvement 3>"],
  "grade_letter": "<A|B|C|D|F>"
}

Rules:
- Be specific — reference actual line numbers and variable names
- Be constructive — every criticism should have a suggested fix
- Be encouraging — always acknowledge what the student did well
- line_comments should cover the most important issues (3-8 comments, not exhaustive)
- overall_score = sum of (criterion score / 10 * weight * 100)
"""


def build_review_prompt(
    code: str,
    assignment_prompt: str,
    rubric: Rubric,
    analysis: AnalysisResult,
    language: str = "python",
) -> str:
    """Assemble the user message sent to Claude."""

    rubric_text = "\n".join(
        f"- {c.name} ({int(c.weight * 100)}%): {c.description}"
        for c in rubric.criteria
    )

    prompt = f"""## Assignment
{assignment_prompt}

## Grading rubric
{rubric_text}

## Static analysis results (pre-computed)
{analysis.summary_text()}

## Student's {language} submission
```{language}
{code}
```

Review this submission against the rubric. Return JSON only."""

    return prompt
