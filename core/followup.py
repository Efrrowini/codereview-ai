"""
Adaptive follow-up generator.
Takes a ReviewResult and generates a personalised exercise
targeting the student's weakest criterion.
"""
import json
import os
from dataclasses import dataclass
from typing import Optional

from groq import Groq
from dotenv import load_dotenv

load_dotenv()

FOLLOWUP_SYSTEM = """You are an expert CS educator. A student just received automated feedback on their code assignment.

Your job is to generate ONE short, targeted follow-up exercise that directly addresses their weakest area.

Respond with valid JSON only. No markdown, no preamble.

Format:
{
  "weak_criterion": "<name of the weakest criterion>",
  "exercise_title": "<short title, max 10 words>",
  "exercise": "<the actual exercise prompt — 2-4 sentences, specific and actionable>",
  "hint": "<one helpful hint without giving away the answer>",
  "expected_skills": ["<skill 1>", "<skill 2>"]
}"""


@dataclass
class FollowUpExercise:
    weak_criterion: str
    exercise_title: str
    exercise: str
    hint: str
    expected_skills: list[str]
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


def generate_followup(
    review_result,
    code: str,
    assignment_prompt: str,
    api_key: Optional[str] = None,
) -> FollowUpExercise:
    """Generate a personalised follow-up exercise from a review result."""

    key = api_key or os.getenv("GROQ_API_KEY")
    if not key:
        return FollowUpExercise(
            weak_criterion="", exercise_title="", exercise="",
            hint="", expected_skills=[],
            error="GROQ_API_KEY not set",
        )

    # Find weakest criterion
    if not review_result.criteria_scores:
        return FollowUpExercise(
            weak_criterion="", exercise_title="", exercise="",
            hint="", expected_skills=[],
            error="No criteria scores available",
        )

    weakest = min(review_result.criteria_scores, key=lambda c: c.score)

    prompt = f"""The student just completed this assignment:
"{assignment_prompt}"

Their code:
```python
{code[:800]}
```

Overall score: {review_result.overall_score:.1f}/100
Their weakest area: {weakest.name} — scored {weakest.score:.1f}/10
Feedback on this area: {weakest.feedback}

Generate a targeted follow-up exercise that helps them improve specifically on {weakest.name}.
Make it concrete, achievable in 15-20 minutes, and directly related to their original assignment."""

    try:
        client = Groq(api_key=key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": FOLLOWUP_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=600,
        )
        raw = response.choices[0].message.content.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        return FollowUpExercise(
            weak_criterion=data.get("weak_criterion", weakest.name),
            exercise_title=data.get("exercise_title", "Follow-up Exercise"),
            exercise=data.get("exercise", ""),
            hint=data.get("hint", ""),
            expected_skills=data.get("expected_skills", []),
        )

    except json.JSONDecodeError as e:
        return FollowUpExercise(
            weak_criterion="", exercise_title="", exercise="",
            hint="", expected_skills=[],
            error=f"JSON parse error: {e}",
        )
    except Exception as e:
        return FollowUpExercise(
            weak_criterion="", exercise_title="", exercise="",
            hint="", expected_skills=[],
            error=f"API error: {e}",
        )