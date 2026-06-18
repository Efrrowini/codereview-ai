from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class RubricCriterion:
    name: str
    weight: float          # 0.0 - 1.0, all weights must sum to 1.0
    description: str
    max_score: int = 10


@dataclass
class Rubric:
    name: str
    criteria: list[RubricCriterion] = field(default_factory=list)
    language: str = "python"
    notes: Optional[str] = None

    def validate(self) -> tuple[bool, str]:
        total = sum(c.weight for c in self.criteria)
        if abs(total - 1.0) > 0.01:
            return False, f"Weights must sum to 1.0 (currently {total:.2f})"
        return True, "ok"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "language": self.language,
            "notes": self.notes,
            "criteria": [
                {
                    "name": c.name,
                    "weight": c.weight,
                    "description": c.description,
                    "max_score": c.max_score,
                }
                for c in self.criteria
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> "Rubric":
        criteria = [
            RubricCriterion(**c) for c in data.get("criteria", [])
        ]
        return cls(
            name=data["name"],
            criteria=criteria,
            language=data.get("language", "python"),
            notes=data.get("notes"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "Rubric":
        return cls.from_dict(json.loads(json_str))


# --- Default rubrics teachers can pick from ---

DEFAULT_PYTHON_RUBRIC = Rubric(
    name="Standard Python Assignment",
    language="python",
    criteria=[
        RubricCriterion(
            name="Correctness",
            weight=0.40,
            description="Does the code produce the correct output for all expected inputs?",
        ),
        RubricCriterion(
            name="Code style",
            weight=0.20,
            description="PEP8 compliance, naming conventions, no dead code.",
        ),
        RubricCriterion(
            name="Efficiency",
            weight=0.20,
            description="Appropriate algorithm choices, no unnecessary loops or redundancy.",
        ),
        RubricCriterion(
            name="Documentation",
            weight=0.20,
            description="Docstrings, inline comments where needed, readable variable names.",
        ),
    ],
)

DEFAULT_DS_RUBRIC = Rubric(
    name="Data Science / ML Assignment",
    language="python",
    criteria=[
        RubricCriterion(
            name="Correctness",
            weight=0.35,
            description="Correct use of libraries, correct pipeline, valid outputs.",
        ),
        RubricCriterion(
            name="Methodology",
            weight=0.30,
            description="Appropriate model choice, train/test split, evaluation metrics.",
        ),
        RubricCriterion(
            name="Code quality",
            weight=0.20,
            description="Clean, readable, reproducible code.",
        ),
        RubricCriterion(
            name="Analysis",
            weight=0.15,
            description="Interpretation of results, commentary on findings.",
        ),
    ],
)

BUILTIN_RUBRICS = {
    DEFAULT_PYTHON_RUBRIC.name: DEFAULT_PYTHON_RUBRIC,
    DEFAULT_DS_RUBRIC.name: DEFAULT_DS_RUBRIC,
}
