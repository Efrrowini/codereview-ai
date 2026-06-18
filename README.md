# CodeReview AI

> AI-powered code assignment reviewer for CS educators. Built for EdTech 3.0 Hackathon — Track 2: Assessment & Feedback Automation.

## What it does

Teachers spend 40% of their time grading. CodeReview AI gives that time back.

Paste a student's code submission + the assignment prompt → get structured, line-level feedback in seconds: correctness score, style issues, efficiency notes, rubric-graded score, and a letter grade. Built for real CS classroom use.

## Architecture

```
Student code + assignment prompt
        ↓
  Static analysis (Pylint + AST)
        ↓
  Prompt builder (context assembly)
        ↓
  Claude API (structured JSON feedback)
        ↓
  Annotated feedback + rubric score
```

## Stack

- **Frontend**: Streamlit
- **Backend**: FastAPI
- **AI**: Claude (claude-sonnet-4-6)
- **Static analysis**: Pylint + Python AST
- **Database**: SQLite + SQLAlchemy
- **Deploy**: Streamlit Cloud

## Local setup

```bash
git clone https://github.com/Efrrowini/codereview-ai
cd codereview-ai
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env

# Run backend
uvicorn backend.main:app --reload

# Run frontend (separate terminal)
streamlit run frontend/app.py
```

## Project structure

```
codereview-ai/
├── backend/
│   ├── main.py          # FastAPI app
│   ├── routes.py        # API endpoints
│   └── models.py        # SQLAlchemy models
├── core/
│   ├── analyzer.py      # Static analysis (Pylint + AST)
│   ├── prompt_builder.py # Claude prompt assembly
│   ├── reviewer.py      # Pipeline orchestrator
│   └── rubric.py        # Rubric engine + defaults
├── frontend/
│   └── app.py           # Streamlit UI
├── tests/
│   └── test_analyzer.py
└── requirements.txt
```

## Built by

Efro — [github.com/Efrrowini](https://github.com/Efrrowini)
