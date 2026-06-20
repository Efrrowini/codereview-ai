from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/codereview.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    student_name = Column(String(200), default="Unknown")   # NEW
    assignment_title = Column(String(200))
    language = Column(String(50), default="python")
    code = Column(Text)
    assignment_prompt = Column(Text)
    rubric_json = Column(Text)
    feedback_json = Column(Text)
    overall_score = Column(Float)
    submitted_at = Column(DateTime, default=datetime.utcnow)


class Rubric(Base):
    __tablename__ = "rubrics"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), unique=True)
    rubric_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)
    # Add student_name column if it doesn't exist (migration)
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE submissions ADD COLUMN student_name VARCHAR(200) DEFAULT 'Unknown'"))
            conn.commit()
    except Exception:
        pass  # Column already exists


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()