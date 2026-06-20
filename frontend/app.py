import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import json
import time
import csv
import io
from collections import defaultdict
from core.reviewer import CodeReviewer
from core.rubric import BUILTIN_RUBRICS, Rubric, RubricCriterion
from core.followup import generate_followup
from backend.models import init_db, SessionLocal, Submission

st.set_page_config(
    page_title="CodeReview AI",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
section[data-testid="stSidebar"] { background: #0D1117; border-right: 1px solid #21262D; }
.page-header { background: #161B22; border: 1px solid #21262D; border-left: 3px solid #00D084; border-radius: 0 10px 10px 0; padding: 20px 24px; margin-bottom: 24px; }
.page-header h1 { font-family: 'Inter', sans-serif; font-size: 20px; font-weight: 600; color: #E6EDF3; margin: 0 0 4px; letter-spacing: -0.3px; }
.page-header p { font-size: 13px; color: #8B949E; margin: 0; }
.grade-badge { display:inline-flex; align-items:center; justify-content:center; width:72px; height:72px; border-radius:12px; font-family:'JetBrains Mono',monospace; font-size:36px; font-weight:700; margin-bottom:16px; border:2px solid; }
.grade-A { background:#0D2818; color:#00D084; border-color:#00D084; }
.grade-B { background:#0D1A2E; color:#00A3FF; border-color:#00A3FF; }
.grade-C { background:#2E1F0D; color:#F0A83A; border-color:#F0A83A; }
.grade-D { background:#2E150D; color:#FF7B54; border-color:#FF7B54; }
.grade-F { background:#2E0D0D; color:#F85149; border-color:#F85149; }
.comment-error      { border-left:3px solid #F85149; padding:8px 14px; margin:6px 0; background:#1C0F0F; border-radius:0 8px 8px 0; font-size:13px; }
.comment-warning    { border-left:3px solid #F0A83A; padding:8px 14px; margin:6px 0; background:#1C150A; border-radius:0 8px 8px 0; font-size:13px; }
.comment-suggestion { border-left:3px solid #00A3FF; padding:8px 14px; margin:6px 0; background:#0A1520; border-radius:0 8px 8px 0; font-size:13px; }
.comment-praise     { border-left:3px solid #00D084; padding:8px 14px; margin:6px 0; background:#0A1C14; border-radius:0 8px 8px 0; font-size:13px; }
.lb-row { display:flex; align-items:center; gap:14px; padding:10px 16px; background:#161B22; border:1px solid #21262D; border-radius:8px; margin-bottom:8px; }
.lb-rank { font-family:'JetBrains Mono',monospace; font-size:13px; color:#8B949E; min-width:28px; }
.lb-name { font-weight:500; color:#E6EDF3; flex:1; font-size:14px; }
.lb-score { font-family:'JetBrains Mono',monospace; font-size:14px; color:#00D084; }
.followup-card { background:linear-gradient(135deg,#0D1A2E,#0D2818); border:1px solid #00D084; border-radius:10px; padding:20px; margin-top:8px; }
.followup-card h3 { color:#00D084; font-family:'JetBrains Mono',monospace; font-size:16px; margin:0 0 10px; }
.followup-card p { color:#C9D1D9; font-size:13px; line-height:1.6; margin:0; }
hr { border-color: #21262D !important; }
div[data-testid="metric-container"] { background:#161B22; border:1px solid #21262D; border-radius:10px; padding:14px 18px; }
div[data-testid="metric-container"] label { color:#8B949E !important; font-size:11px !important; text-transform:uppercase; letter-spacing:.05em; }
div[data-testid="metric-container"] div[data-testid="metric-value"] { font-family:'JetBrains Mono',monospace; color:#E6EDF3 !important; }
.stButton > button[kind="primary"] { background:#00D084 !important; color:#0D1117 !important; border:none !important; font-weight:600 !important; border-radius:8px !important; }
.stButton > button[kind="primary"]:hover { background:#00B872 !important; }
.stTextInput input, .stTextArea textarea { background:#161B22 !important; border:1px solid #21262D !important; border-radius:8px !important; color:#E6EDF3 !important; }
.stTextInput input:focus, .stTextArea textarea:focus { border-color:#00D084 !important; box-shadow:0 0 0 2px rgba(0,208,132,0.15) !important; }
</style>
""", unsafe_allow_html=True)


def get_grade(score):
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"

def save_submission(title, language, code, prompt, rubric, result, student_name="Unknown"):
    try:
        db = SessionLocal()
        sub = Submission(
            student_name=student_name,
            assignment_title=title or "Untitled",
            language=language, code=code,
            assignment_prompt=prompt,
            rubric_json=rubric.to_json(),
            feedback_json=json.dumps(result.raw_json),
            overall_score=result.overall_score,
        )
        db.add(sub); db.commit(); db.close()
    except Exception:
        pass

def get_api_key():
    try:
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return os.getenv("GROQ_API_KEY", "")


# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('''<div style="padding:12px 0 8px;"><span style="font-family:JetBrains Mono,monospace;font-size:16px;font-weight:600;color:#E6EDF3;">⟩ CodeReview</span><span style="font-family:JetBrains Mono,monospace;font-size:16px;font-weight:600;color:#00D084;">AI</span></div><div style="font-size:11px;color:#8B949E;margin-bottom:8px;">AI code reviewer for CS educators</div>''', unsafe_allow_html=True)
    st.divider()

    page = st.radio("Navigate", ["📝 Review", "📦 Batch Review", "📚 History", "📈 Progress", "🏫 Dashboard"], index=0, label_visibility="collapsed")

    st.divider()
    default_key = get_api_key()
    api_key = st.text_input("Groq API Key", type="password", value=default_key,
                             placeholder="gsk_...", help="Get your free key at console.groq.com")

    st.divider()
    st.subheader("Rubric")
    rubric_choice = st.radio("Choose rubric", ["Standard Python", "Data Science / ML", "Custom"], index=0)

    rubric = None
    if rubric_choice == "Standard Python":
        rubric = BUILTIN_RUBRICS["Standard Python Assignment"]
        st.caption("Correctness 40% · Style 20% · Efficiency 20% · Docs 20%")
    elif rubric_choice == "Data Science / ML":
        rubric = BUILTIN_RUBRICS["Data Science / ML Assignment"]
        st.caption("Correctness 35% · Methodology 30% · Quality 20% · Analysis 15%")
    else:
        st.caption("Weights must sum to 100%")
        c1 = st.slider("Correctness %", 0, 100, 40, 5)
        c2 = st.slider("Code Style %",  0, 100, 20, 5)
        c3 = st.slider("Efficiency %",  0, 100, 20, 5)
        c4 = st.slider("Documentation %", 0, 100, 20, 5)
        total = c1 + c2 + c3 + c4
        if total != 100:
            st.error(f"Weights sum to {total}% — must be 100%")
        else:
            rubric = Rubric(name="Custom", criteria=[
                RubricCriterion("Correctness",   c1/100, "Correct output"),
                RubricCriterion("Code style",    c2/100, "PEP8, naming"),
                RubricCriterion("Efficiency",    c3/100, "Appropriate algorithms"),
                RubricCriterion("Documentation", c4/100, "Docstrings and comments"),
            ])

    st.divider()
    language = st.selectbox("Language", ["python", "javascript", "java"], index=0)
    st.divider()
    st.caption("EdTech 3.0 Hackathon · Track 2")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SINGLE REVIEW
# ══════════════════════════════════════════════════════════════════════════════
if "Review" in page and "Batch" not in page:
    st.markdown('''<div class="page-header"><h1>Review Code</h1><p>Paste student code, select a rubric, get AI feedback in seconds</p></div>''', unsafe_allow_html=True)
    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        student_name      = st.text_input("Student name", placeholder="e.g. Alice Johnson")
        assignment_title  = st.text_input("Assignment title", placeholder="e.g. Bubble Sort Implementation")
        assignment_prompt = st.text_area("Assignment prompt", placeholder="Describe what the student was asked to do...", height=100)
        st.markdown("**Student Code**")
        code = st.text_area("code", placeholder="def bubble_sort(arr):\n    ...", height=280, label_visibility="collapsed")
        submitted = st.button("🚀 Review Code", type="primary", use_container_width=True)

    with col2:
        st.subheader("📊 Feedback")
        if submitted:
            if not api_key:   st.error("Please enter your Groq API key in the sidebar.")
            elif not code.strip():   st.error("Please paste some code to review.")
            elif not assignment_prompt.strip(): st.error("Please enter the assignment prompt.")
            elif rubric is None: st.error("Custom rubric weights must sum to 100%.")
            else:
                with st.spinner("Analyzing code... ~10 seconds"):
                    try:
                        reviewer = CodeReviewer(api_key=api_key)
                        result   = reviewer.review(code=code, assignment_prompt=assignment_prompt, rubric=rubric, language=language)
                    except Exception as e:
                        st.error(f"Error: {e}"); result = None

                if result and result.success:
                    save_submission(assignment_title, language, code, assignment_prompt, rubric, result, student_name or "Unknown")

                    m1, m2, m3 = st.columns(3)
                    m1.metric("Overall Score", f"{result.overall_score:.1f}/100")
                    m2.metric("Grade", result.grade_letter)
                    sa = result.static_analysis
                    m3.metric("Static Issues", len(sa.issues) if sa else 0)

                    grade_class = f"grade-{result.grade_letter[0]}"
                    st.markdown(f'<div class="grade-badge {grade_class}">{result.grade_letter}</div>', unsafe_allow_html=True)
                    st.markdown(f"**Summary:** {result.summary}")
                    st.divider()

                    st.subheader("📐 Rubric Breakdown")
                    for cs in result.criteria_scores:
                        st.markdown(f"**{cs.name}** ({int(cs.weight*100)}%) — {cs.score:.1f}/10")
                        st.progress(cs.score / 10)
                        st.caption(cs.feedback)
                    st.divider()

                    if result.line_comments:
                        st.subheader("📍 Line Comments")
                        for lc in result.line_comments:
                            icon = {"error":"🔴","warning":"🟡","suggestion":"🔵","praise":"🟢"}.get(lc.type,"⚪")
                            st.markdown(f'<div class="comment-{lc.type}">{icon} <strong>Line {lc.line}</strong> — {lc.comment}</div>', unsafe_allow_html=True)
                        st.divider()

                    scol, icol = st.columns(2)
                    with scol:
                        st.subheader("✅ Strengths")
                        for s in result.strengths: st.markdown(f"- {s}")
                    with icol:
                        st.subheader("🔧 Improvements")
                        for i in result.improvements: st.markdown(f"- {i}")

                    st.divider()
                    export_data = {
                        "student": student_name, "assignment": assignment_title,
                        "score": result.overall_score, "grade": result.grade_letter,
                        "summary": result.summary,
                        "criteria": [{"name": cs.name, "score": cs.score, "feedback": cs.feedback} for cs in result.criteria_scores],
                        "strengths": result.strengths, "improvements": result.improvements,
                    }
                    st.download_button("⬇️ Export Feedback as JSON",
                        data=json.dumps(export_data, indent=2),
                        file_name=f"feedback_{student_name or 'student'}_{assignment_title or 'review'}.json",
                        mime="application/json")

                    st.divider()
                    st.subheader("🎯 Adaptive Follow-up Exercise")
                    st.caption("Personalised next step based on this student's weakest area")
                    with st.spinner("Generating personalised exercise..."):
                        followup = generate_followup(result, code, assignment_prompt, api_key)
                    if followup.success:
                        weak_score = min(result.criteria_scores, key=lambda c: c.score) if result.criteria_scores else None
                        weak_label = f"{followup.weak_criterion} — {weak_score.score:.1f}/10" if weak_score else followup.weak_criterion
                        skills_html = " &nbsp;·&nbsp; ".join(f'<code style="background:#0D2818;color:#00D084;padding:2px 8px;border-radius:4px;font-size:11px;">{s}</code>' for s in followup.expected_skills)
                        st.markdown(f'''
<div class="followup-card">
  <div style="font-size:11px;color:#8B949E;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px;">🎯 Adaptive Follow-up · Targeting: {weak_label}</div>
  <h3>{followup.exercise_title}</h3>
  <p>{followup.exercise}</p>
  <div style="margin-top:14px;padding-top:14px;border-top:1px solid #1B3A2A;">
    <span style="font-size:11px;color:#8B949E;">Skills practised: </span>{skills_html}
  </div>
</div>''', unsafe_allow_html=True)
                        with st.expander("💡 Hint"):
                            st.markdown(followup.hint)
                    else:
                        st.warning(f"Could not generate follow-up: {followup.error}")

                elif result:
                    st.error(f"Review failed: {result.error}")
        else:
            st.info("Fill in the assignment details and paste the student's code, then click **Review Code**.")
            with st.expander("See an example"):
                st.markdown("**Assignment:** Implement bubble sort")
                st.code('''def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr''', language="python")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: BATCH REVIEW
# ══════════════════════════════════════════════════════════════════════════════
elif "Batch" in page:
    st.markdown('''<div class="page-header"><h1>Batch Review</h1><p>Upload a CSV — review an entire class in minutes</p></div>''', unsafe_allow_html=True)

    with st.expander("📋 CSV format guide"):
        st.markdown("Your CSV must have these columns:")
        st.code("student_name,code", language="text")
        st.download_button("⬇️ Download sample CSV",
            data='student_name,code\nAlice,"def add(a, b): return a + b"\nBob,"def add(a,b):\n    result = a + b\n    return result"\nCharlie,"def add(x,y):\n    # adds two numbers\n    return x+y"',
            file_name="sample_batch.csv", mime="text/csv")

    assignment_prompt_batch = st.text_area("Assignment prompt (applies to all students)",
                                            placeholder="e.g. Write a function that adds two numbers.", height=100)
    uploaded_file = st.file_uploader("Upload student submissions CSV", type=["csv"])

    if uploaded_file and assignment_prompt_batch.strip():
        try:
            content  = uploaded_file.read().decode("utf-8")
            reader   = csv.DictReader(io.StringIO(content))
            students = list(reader)
            st.success(f"Loaded {len(students)} student submissions.")

            if st.button("🚀 Run Batch Review", type="primary"):
                if not api_key:
                    st.error("Please enter your Groq API key in the sidebar.")
                elif rubric is None:
                    st.error("Custom rubric weights must sum to 100%.")
                else:
                    results_data = []
                    progress_bar = st.progress(0)
                    status_text  = st.empty()
                    reviewer = CodeReviewer(api_key=api_key)

                    for idx, student in enumerate(students):
                        name = student.get("student_name", f"Student {idx+1}")
                        code = student.get("code", "")
                        status_text.markdown(f"Reviewing **{name}** ({idx+1}/{len(students)})...")
                        try:
                            result = reviewer.review(code=code, assignment_prompt=assignment_prompt_batch, rubric=rubric, language=language)
                            save_submission(f"Batch Assignment", language, code, assignment_prompt_batch, rubric, result, name)
                            results_data.append({
                                "student": name, "score": result.overall_score if result.success else 0,
                                "grade": result.grade_letter if result.success else "F",
                                "summary": result.summary if result.success else result.error,
                                "strengths": result.strengths if result.success else [],
                                "improvements": result.improvements if result.success else [],
                                "success": result.success,
                            })
                        except Exception as e:
                            results_data.append({"student": name, "score": 0, "grade": "F", "summary": str(e), "strengths": [], "improvements": [], "success": False})
                        progress_bar.progress((idx + 1) / len(students))
                        time.sleep(1)

                    status_text.markdown("✅ All submissions reviewed!")
                    scores = [r["score"] for r in results_data if r["success"]]
                    st.divider()
                    s1, s2, s3, s4 = st.columns(4)
                    s1.metric("Total Reviewed", len(results_data))
                    s2.metric("Average Score", f"{sum(scores)/len(scores):.1f}" if scores else "—")
                    s3.metric("Highest", f"{max(scores):.1f}" if scores else "—")
                    s4.metric("Lowest",  f"{min(scores):.1f}" if scores else "—")

                    st.divider()
                    for r in sorted(results_data, key=lambda x: x["score"], reverse=True):
                        grade_emoji = {"A":"🟢","B":"🟢","C":"🟡","D":"🟠","F":"🔴"}.get(r["grade"],"⚪")
                        with st.expander(f"{grade_emoji} {r['student']} — {r['score']:.1f}/100 · Grade {r['grade']}"):
                            st.markdown(f"**Summary:** {r['summary']}")
                            sc, ic = st.columns(2)
                            with sc:
                                st.markdown("**✅ Strengths**")
                                for s in r["strengths"]: st.markdown(f"- {s}")
                            with ic:
                                st.markdown("**🔧 Improvements**")
                                for i in r["improvements"]: st.markdown(f"- {i}")

                    # ── Plagiarism similarity check ──────────────────────
                    st.divider()
                    st.markdown('''<div class="page-header"><h1>🔍 Similarity Check</h1><p>Flagging suspiciously similar submissions using cosine similarity</p></div>''', unsafe_allow_html=True)

                    from sklearn.feature_extraction.text import TfidfVectorizer
                    from sklearn.metrics.pairwise import cosine_similarity
                    import numpy as np

                    codes = [s.get("code", "") for s in students]
                    names = [s.get("student_name", f"Student {i+1}") for i, s in enumerate(students)]

                    try:
                        vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 5))
                        tfidf_matrix = vectorizer.fit_transform(codes)
                        sim_matrix = cosine_similarity(tfidf_matrix)

                        THRESHOLD = 0.75
                        flagged_pairs = []
                        for i in range(len(names)):
                            for j in range(i+1, len(names)):
                                sim = sim_matrix[i][j]
                                if sim >= THRESHOLD:
                                    flagged_pairs.append((names[i], names[j], sim))

                        if flagged_pairs:
                            st.warning(f"⚠️ {len(flagged_pairs)} suspicious pair(s) detected above {int(THRESHOLD*100)}% similarity threshold.")
                            for a, b, sim in sorted(flagged_pairs, key=lambda x: x[2], reverse=True):
                                sim_pct = int(sim * 100)
                                color = "#F85149" if sim_pct >= 90 else "#F0A83A"
                                st.markdown(f'''<div style="background:#161B22;border:1px solid {color};border-left:4px solid {color};border-radius:8px;padding:12px 16px;margin:6px 0;display:flex;justify-content:space-between;align-items:center;">
                                    <span style="color:#E6EDF3;font-size:14px;">⚠️ <strong>{a}</strong> &nbsp;↔&nbsp; <strong>{b}</strong></span>
                                    <span style="font-family:JetBrains Mono,monospace;color:{color};font-size:14px;font-weight:600;">{sim_pct}% similar</span>
                                </div>''', unsafe_allow_html=True)
                        else:
                            st.success("✅ No suspicious similarities detected above 75% threshold.")

                    except Exception as e:
                        st.info(f"Similarity check skipped: install scikit-learn to enable this feature.")

                    st.divider()
                    csv_out = io.StringIO()
                    writer  = csv.writer(csv_out)
                    writer.writerow(["Student", "Score", "Grade", "Summary"])
                    for r in results_data:
                        writer.writerow([r["student"], r["score"], r["grade"], r["summary"]])
                    st.download_button("⬇️ Download Full Report (CSV)", data=csv_out.getvalue(),
                        file_name="batch_report.csv", mime="text/csv")
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
    else:
        if not uploaded_file:
            st.info("Upload a CSV file to get started.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: HISTORY
# ══════════════════════════════════════════════════════════════════════════════
elif "History" in page:
    st.markdown('''<div class="page-header"><h1>Submission History</h1><p>All past reviews — searchable, expandable, exportable</p></div>''', unsafe_allow_html=True)
    try:
        db = SessionLocal()
        submissions = db.query(Submission).order_by(Submission.submitted_at.desc()).limit(50).all()
        db.close()
    except Exception as e:
        st.error(f"Could not load history: {e}"); submissions = []

    if not submissions:
        st.info("No submissions yet. Go to the Review page to get started.")
    else:
        scores = [s.overall_score for s in submissions if s.overall_score]
        s1, s2, s3 = st.columns(3)
        s1.metric("Total Reviews", len(submissions))
        s2.metric("Average Score", f"{sum(scores)/len(scores):.1f}" if scores else "—")
        s3.metric("Highest Score", f"{max(scores):.1f}" if scores else "—")
        st.divider()
        for sub in submissions:
            grade = get_grade(sub.overall_score or 0)
            icon  = "🟢" if (sub.overall_score or 0) >= 70 else "🔴"
            student_label = f"{sub.student_name} — " if sub.student_name and sub.student_name != "Unknown" else ""
            with st.expander(f"{icon} {student_label}{sub.assignment_title} — {sub.overall_score:.1f}/100 · {sub.submitted_at.strftime('%d %b %Y, %H:%M')}"):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown(f"**Student:** {sub.student_name}")
                    st.markdown(f"**Language:** {sub.language}")
                    if sub.feedback_json:
                        feedback = json.loads(sub.feedback_json)
                        st.markdown(f"**Summary:** {feedback.get('summary','')}")
                with c2:
                    st.markdown(f'<div class="grade-badge grade-{grade}" style="font-size:32px;padding:6px 18px;">{grade}</div>', unsafe_allow_html=True)
                    st.metric("Score", f"{sub.overall_score:.1f}/100")
                st.code(sub.code[:500] + ("..." if len(sub.code) > 500 else ""), language=sub.language)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: PROGRESS TRACKER
# ══════════════════════════════════════════════════════════════════════════════
elif "Progress" in page:
    st.markdown('''<div class="page-header"><h1>Student Progress</h1><p>Track how individual students improve across assignments</p></div>''', unsafe_allow_html=True)

    try:
        db = SessionLocal()
        submissions = db.query(Submission).order_by(Submission.submitted_at.asc()).all()
        db.close()
    except Exception as e:
        st.error(f"Could not load data: {e}"); submissions = []

    if not submissions:
        st.info("No submissions yet. Review some code first.")
    else:
        # Group by student
        student_data = defaultdict(list)
        for sub in submissions:
            name = sub.student_name or "Unknown"
            if name != "Unknown":
                student_data[name].append({
                    "assignment": sub.assignment_title,
                    "score": sub.overall_score or 0,
                    "date": sub.submitted_at,
                    "grade": get_grade(sub.overall_score or 0),
                })

        if not student_data:
            st.info("No named student submissions yet. Add student names when reviewing to track progress.")
        else:
            # Class overview
            st.subheader("🏫 Class Overview")
            all_scores = [sub.overall_score for sub in submissions if sub.overall_score]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Students", len(student_data))
            c2.metric("Total Reviews", len(submissions))
            c3.metric("Class Average", f"{sum(all_scores)/len(all_scores):.1f}" if all_scores else "—")

            # Count improvements
            improved = sum(
                1 for subs in student_data.values()
                if len(subs) >= 2 and subs[-1]["score"] > subs[0]["score"]
            )
            c4.metric("Students Improving", f"{improved}/{len(student_data)}")

            st.divider()

            # Individual student selector
            st.subheader("👤 Individual Student Progress")
            selected_student = st.selectbox("Select student", sorted(student_data.keys()))

            if selected_student:
                subs = student_data[selected_student]

                if len(subs) == 1:
                    st.info(f"{selected_student} has only 1 submission. Submit more assignments to see progress over time.")
                    s1, s2 = st.columns(2)
                    s1.metric("Score", f"{subs[0]['score']:.1f}/100")
                    s2.metric("Grade", subs[0]['grade'])
                else:
                    first_score = subs[0]["score"]
                    last_score  = subs[-1]["score"]
                    delta       = last_score - first_score

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("First Score", f"{first_score:.1f}/100")
                    m2.metric("Latest Score", f"{last_score:.1f}/100", delta=f"{delta:+.1f}")
                    m3.metric("Best Score", f"{max(s['score'] for s in subs):.1f}/100")
                    m4.metric("Assignments", len(subs))

                    # Score over time chart using st.line_chart
                    chart_data = {
                        "Assignment": [s["assignment"] for s in subs],
                        "Score": [s["score"] for s in subs],
                    }

                    st.markdown("**Score progression:**")

                    # Build chart with target line
                    import pandas as pd
                    df = pd.DataFrame({
                        "Score": [s["score"] for s in subs],
                        "Target (70)": [70.0] * len(subs),
                    }, index=[f"#{i+1} {s['assignment'][:20]}" for i, s in enumerate(subs)])

                    st.line_chart(df, height=300)

                    # Assignment breakdown
                    st.markdown("**Assignment history:**")
                    for i, s in enumerate(subs):
                        grade_class = f"grade-{s['grade']}"
                        trend = ""
                        if i > 0:
                            diff = s["score"] - subs[i-1]["score"]
                            trend = f" ({'▲' if diff > 0 else '▼'} {abs(diff):.1f})"
                        col_a, col_b, col_c = st.columns([3, 1, 1])
                        col_a.markdown(f"**{s['assignment']}**")
                        col_b.markdown(f"{s['score']:.1f}/100{trend}")
                        col_c.markdown(f'<div class="grade-badge grade-{s["grade"]}" style="font-size:16px;padding:3px 10px;">{s["grade"]}</div>', unsafe_allow_html=True)

            st.divider()

            # Full class leaderboard
            st.subheader("🏆 Class Leaderboard")
            leaderboard = []
            for name, subs in student_data.items():
                latest = subs[-1]["score"]
                best   = max(s["score"] for s in subs)
                trend  = subs[-1]["score"] - subs[0]["score"] if len(subs) > 1 else 0
                leaderboard.append({"Student": name, "Latest": latest, "Best": best, "Trend": trend, "Submissions": len(subs)})

            leaderboard.sort(key=lambda x: x["Latest"], reverse=True)
            for i, row in enumerate(leaderboard):
                medal = ["🥇","🥈","🥉"][i] if i < 3 else f"#{i+1}"
                trend_str = f"▲ {row['Trend']:.1f}" if row["Trend"] > 0 else (f"▼ {abs(row['Trend']):.1f}" if row["Trend"] < 0 else "—")
                st.markdown(f"{medal} **{row['Student']}** — {row['Latest']:.1f}/100 · Best: {row['Best']:.1f} · Trend: {trend_str} · {row['Submissions']} submissions")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: CLASS DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
elif "Dashboard" in page:
    st.markdown('''<div class="page-header"><h1>Class Dashboard</h1><p>Grade distribution, common weaknesses, and class-wide trends</p></div>''', unsafe_allow_html=True)

    try:
        db = SessionLocal()
        submissions = db.query(Submission).order_by(Submission.submitted_at.asc()).all()
        db.close()
    except Exception as e:
        st.error(f"Could not load data: {e}"); submissions = []

    if not submissions:
        st.info("No submissions yet. Review some code first.")
    else:
        import pandas as pd

        scores = [s.overall_score for s in submissions if s.overall_score]
        grades = [get_grade(s) for s in scores]

        # Top metrics
        st.subheader("📊 Class Summary")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Submissions", len(submissions))
        m2.metric("Class Average", f"{sum(scores)/len(scores):.1f}" if scores else "—")
        m3.metric("Highest Score", f"{max(scores):.1f}" if scores else "—")
        m4.metric("Lowest Score",  f"{min(scores):.1f}" if scores else "—")
        passing = sum(1 for s in scores if s >= 70)
        m5.metric("Pass Rate", f"{passing/len(scores)*100:.0f}%" if scores else "—")

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📈 Grade Distribution")
            grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
            for s in scores:
                grade_counts[get_grade(s)] += 1
            df_grades = pd.DataFrame({
                "Grade": list(grade_counts.keys()),
                "Count": list(grade_counts.values()),
            })
            st.bar_chart(df_grades.set_index("Grade"))

        with col2:
            st.subheader("📉 Score Distribution")
            bins = {"0-49": 0, "50-59": 0, "60-69": 0, "70-79": 0, "80-89": 0, "90-100": 0}
            for s in scores:
                if s < 50: bins["0-49"] += 1
                elif s < 60: bins["50-59"] += 1
                elif s < 70: bins["60-69"] += 1
                elif s < 80: bins["70-79"] += 1
                elif s < 90: bins["80-89"] += 1
                else: bins["90-100"] += 1
            df_dist = pd.DataFrame({"Range": list(bins.keys()), "Students": list(bins.values())})
            st.bar_chart(df_dist.set_index("Range"))

        st.divider()

        # Common weaknesses from feedback
        st.subheader("🔍 Most Common Weaknesses")
        weakness_counts = defaultdict(int)
        for sub in submissions:
            if sub.feedback_json:
                try:
                    feedback = json.loads(sub.feedback_json)
                    for criterion in feedback.get("criteria_scores", []):
                        if criterion.get("score", 10) < 7:
                            weakness_counts[criterion["name"]] += 1
                except Exception:
                    pass

        if weakness_counts:
            sorted_weaknesses = sorted(weakness_counts.items(), key=lambda x: x[1], reverse=True)
            df_weak = pd.DataFrame(sorted_weaknesses, columns=["Criterion", "Times Weak"])
            st.bar_chart(df_weak.set_index("Criterion"))
            st.caption("Criteria where students scored below 7/10")
        else:
            st.info("Not enough feedback data yet.")

        st.divider()

        # Score trend over time
        st.subheader("📅 Class Score Trend Over Time")
        if len(submissions) >= 2:
            df_trend = pd.DataFrame({
                "Score": [s.overall_score for s in submissions if s.overall_score],
            }, index=[s.submitted_at.strftime("%d %b %H:%M") for s in submissions if s.overall_score])
            st.line_chart(df_trend)
        else:
            st.info("Need at least 2 submissions to show trend.")