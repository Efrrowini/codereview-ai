import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import json
import time
import csv
import io
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
.grade-badge {
    display: inline-block;
    padding: 8px 24px;
    border-radius: 8px;
    font-size: 48px;
    font-weight: bold;
    text-align: center;
    margin-bottom: 12px;
}
.grade-A { background: #EAF3DE; color: #27500A; }
.grade-B { background: #E6F1FB; color: #0C447C; }
.grade-C { background: #FAEEDA; color: #633806; }
.grade-D { background: #FAECE7; color: #712B13; }
.grade-F { background: #FCEBEB; color: #791F1F; }
.comment-error      { border-left: 4px solid #E24B4A; padding: 6px 12px; margin: 4px 0; background: #FCEBEB; border-radius: 0 6px 6px 0; }
.comment-warning    { border-left: 4px solid #EF9F27; padding: 6px 12px; margin: 4px 0; background: #FAEEDA; border-radius: 0 6px 6px 0; }
.comment-suggestion { border-left: 4px solid #378ADD; padding: 6px 12px; margin: 4px 0; background: #E6F1FB; border-radius: 0 6px 6px 0; }
.comment-praise     { border-left: 4px solid #1D9E75; padding: 6px 12px; margin: 4px 0; background: #E1F5EE; border-radius: 0 6px 6px 0; }
.batch-row-pass { background: #1a2e1a; border-left: 4px solid #1D9E75; border-radius: 6px; padding: 10px 14px; margin: 6px 0; }
.batch-row-fail { background: #2e1a1a; border-left: 4px solid #E24B4A; border-radius: 6px; padding: 10px 14px; margin: 6px 0; }
</style>
""", unsafe_allow_html=True)


# ── helpers ──────────────────────────────────────────────────────────────────
def get_grade(score):
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"

def save_submission(title, language, code, prompt, rubric, result):
    try:
        db = SessionLocal()
        sub = Submission(
            assignment_title=title or "Untitled",
            language=language,
            code=code,
            assignment_prompt=prompt,
            rubric_json=rubric.to_json(),
            feedback_json=json.dumps(result.raw_json),
            overall_score=result.overall_score,
        )
        db.add(sub)
        db.commit()
        db.close()
    except Exception:
        pass


# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔍 CodeReview AI")
    st.caption("AI-powered code reviewer for CS educators")
    st.divider()

    page = st.radio("Navigate", ["📝 Review", "📦 Batch Review", "📚 History"], index=0, label_visibility="collapsed")

    st.divider()
    api_key = st.text_input("Groq API Key", type="password", placeholder="gsk_...",
                             help="Get your free key at console.groq.com")

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
    st.title("📝 Review Code")

    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        assignment_title  = st.text_input("Assignment title", placeholder="e.g. Bubble Sort Implementation")
        assignment_prompt = st.text_area("Assignment prompt",
                                         placeholder="Describe what the student was asked to do...", height=120)
        st.markdown("**Student Code**")
        code = st.text_area("code", placeholder="def bubble_sort(arr):\n    ...",
                             height=300, label_visibility="collapsed")
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
                        result   = reviewer.review(code=code, assignment_prompt=assignment_prompt,
                                                   rubric=rubric, language=language)
                    except Exception as e:
                        st.error(f"Error: {e}"); result = None

                if result and result.success:
                    save_submission(assignment_title, language, code, assignment_prompt, rubric, result)

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
                        "assignment": assignment_title, "score": result.overall_score,
                        "grade": result.grade_letter, "summary": result.summary,
                        "criteria": [{"name": cs.name, "score": cs.score, "feedback": cs.feedback} for cs in result.criteria_scores],
                        "strengths": result.strengths, "improvements": result.improvements,
                    }
                    st.download_button("⬇️ Export Feedback as JSON",
                        data=json.dumps(export_data, indent=2),
                        file_name=f"feedback_{assignment_title or 'review'}.json",
                        mime="application/json")

                    # Adaptive follow-up exercise
                    st.divider()
                    st.subheader("🎯 Adaptive Follow-up Exercise")
                    st.caption("Personalised next step based on this student's weakest area")
                    with st.spinner("Generating personalised exercise..."):
                        followup = generate_followup(
                            review_result=result,
                            code=code,
                            assignment_prompt=assignment_prompt,
                            api_key=api_key,
                        )
                    if followup.success:
                        weak_score = min(result.criteria_scores, key=lambda c: c.score) if result.criteria_scores else None
                        st.markdown(f"**Targeting weak area:** {followup.weak_criterion} "
                                    f"({weak_score.score:.1f}/10)" if weak_score else f"**Targeting:** {followup.weak_criterion}")
                        st.markdown(f"### {followup.exercise_title}")
                        st.info(followup.exercise)
                        with st.expander("💡 Hint"):
                            st.markdown(followup.hint)
                        if followup.expected_skills:
                            st.markdown("**Skills practised:** " + " · ".join(f"`{s}`" for s in followup.expected_skills))
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
    st.title("📦 Batch Review")
    st.markdown("Upload a CSV of student submissions — get all of them reviewed at once.")

    with st.expander("📋 CSV format guide"):
        st.markdown("Your CSV must have these columns:")
        st.code("student_name,code", language="text")
        st.markdown("Example:")
        st.code('''student_name,code
Alice,"def add(a, b): return a + b"
Bob,"def add(a,b):\n    result = a + b\n    return result"
Charlie,"def add(x,y):\n    # adds two numbers\n    return x+y"''', language="text")
        st.download_button("⬇️ Download sample CSV",
            data='student_name,code\nAlice,"def add(a, b): return a + b"\nBob,"def add(a,b):\n    result = a + b\n    return result"\nCharlie,"def add(x,y):\n    # adds two numbers\n    return x+y"',
            file_name="sample_batch.csv", mime="text/csv")

    assignment_prompt_batch = st.text_area("Assignment prompt (applies to all students)",
                                            placeholder="e.g. Write a function that adds two numbers and returns the result.",
                                            height=100)
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
                            result = reviewer.review(
                                code=code,
                                assignment_prompt=assignment_prompt_batch,
                                rubric=rubric,
                                language=language,
                            )
                            save_submission(f"Batch - {name}", language, code, assignment_prompt_batch, rubric, result)
                            results_data.append({
                                "student": name,
                                "score": result.overall_score if result.success else 0,
                                "grade": result.grade_letter if result.success else "F",
                                "summary": result.summary if result.success else result.error,
                                "strengths": result.strengths if result.success else [],
                                "improvements": result.improvements if result.success else [],
                                "success": result.success,
                            })
                        except Exception as e:
                            results_data.append({
                                "student": name, "score": 0, "grade": "F",
                                "summary": str(e), "strengths": [], "improvements": [], "success": False,
                            })

                        progress_bar.progress((idx + 1) / len(students))
                        time.sleep(1)  # rate limit buffer

                    status_text.markdown("✅ All submissions reviewed!")

                    # Summary stats
                    scores = [r["score"] for r in results_data if r["success"]]
                    st.divider()
                    s1, s2, s3, s4 = st.columns(4)
                    s1.metric("Total Reviewed", len(results_data))
                    s2.metric("Average Score", f"{sum(scores)/len(scores):.1f}" if scores else "—")
                    s3.metric("Highest", f"{max(scores):.1f}" if scores else "—")
                    s4.metric("Lowest",  f"{min(scores):.1f}" if scores else "—")

                    st.divider()
                    st.subheader("Results")
                    for r in sorted(results_data, key=lambda x: x["score"], reverse=True):
                        row_class = "batch-row-pass" if r["score"] >= 70 else "batch-row-fail"
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

                    # Export full report
                    st.divider()
                    csv_out = io.StringIO()
                    writer  = csv.writer(csv_out)
                    writer.writerow(["Student", "Score", "Grade", "Summary"])
                    for r in results_data:
                        writer.writerow([r["student"], r["score"], r["grade"], r["summary"]])
                    st.download_button("⬇️ Download Full Report (CSV)",
                        data=csv_out.getvalue(),
                        file_name="batch_report.csv",
                        mime="text/csv")

        except Exception as e:
            st.error(f"Error reading CSV: {e}")
    else:
        if not uploaded_file:
            st.info("Upload a CSV file to get started.")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: HISTORY
# ══════════════════════════════════════════════════════════════════════════════
elif "History" in page:
    st.title("📚 Submission History")
    st.caption("All past reviews saved locally")

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
            with st.expander(f"{icon} {sub.assignment_title} — {sub.overall_score:.1f}/100 · {sub.submitted_at.strftime('%d %b %Y, %H:%M')}"):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown(f"**Language:** {sub.language}")
                    st.markdown(f"**Prompt:** {sub.assignment_prompt[:200]}...")
                    if sub.feedback_json:
                        feedback = json.loads(sub.feedback_json)
                        st.markdown(f"**Summary:** {feedback.get('summary','')}")
                with c2:
                    grade_class = f"grade-{grade}"
                    st.markdown(f'<div class="grade-badge {grade_class}" style="font-size:32px;padding:6px 18px;">{grade}</div>', unsafe_allow_html=True)
                    st.metric("Score", f"{sub.overall_score:.1f}/100")
                st.code(sub.code[:500] + ("..." if len(sub.code) > 500 else ""), language=sub.language)