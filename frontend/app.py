import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import json
from core.reviewer import CodeReviewer
from core.rubric import BUILTIN_RUBRICS, DEFAULT_PYTHON_RUBRIC, Rubric, RubricCriterion

# --- Page config ---
st.set_page_config(
    page_title="CodeReview AI",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Custom CSS ---
st.markdown("""
<style>
.grade-badge {
    display: inline-block;
    padding: 8px 24px;
    border-radius: 8px;
    font-size: 48px;
    font-weight: bold;
    text-align: center;
}
.grade-A { background: #EAF3DE; color: #27500A; }
.grade-B { background: #E6F1FB; color: #0C447C; }
.grade-C { background: #FAEEDA; color: #633806; }
.grade-D { background: #FAECE7; color: #712B13; }
.grade-F { background: #FCEBEB; color: #791F1F; }
.comment-error   { border-left: 4px solid #E24B4A; padding: 6px 12px; margin: 4px 0; background: #FCEBEB; border-radius: 0 6px 6px 0; }
.comment-warning { border-left: 4px solid #EF9F27; padding: 6px 12px; margin: 4px 0; background: #FAEEDA; border-radius: 0 6px 6px 0; }
.comment-suggestion { border-left: 4px solid #378ADD; padding: 6px 12px; margin: 4px 0; background: #E6F1FB; border-radius: 0 6px 6px 0; }
.comment-praise  { border-left: 4px solid #1D9E75; padding: 6px 12px; margin: 4px 0; background: #E1F5EE; border-radius: 0 6px 6px 0; }
</style>
""", unsafe_allow_html=True)


# --- Sidebar ---
with st.sidebar:
    st.title("⚙️ Configuration")

    api_key = st.text_input(
        "Groq API Key",
        type="password",
        placeholder="gsk_...",
        help="Get your free key at console.groq.com",
    )

    st.divider()

    st.subheader("Rubric")
    rubric_choice = st.radio(
        "Choose rubric",
        ["Standard Python", "Data Science / ML", "Custom"],
        index=0,
    )

    rubric = None
    if rubric_choice == "Standard Python":
        rubric = BUILTIN_RUBRICS["Standard Python Assignment"]
        st.caption("Correctness 40% · Style 20% · Efficiency 20% · Docs 20%")
    elif rubric_choice == "Data Science / ML":
        rubric = BUILTIN_RUBRICS["Data Science / ML Assignment"]
        st.caption("Correctness 35% · Methodology 30% · Quality 20% · Analysis 15%")
    else:
        st.caption("Define custom weights below (must sum to 100%)")
        c1 = st.slider("Correctness %", 0, 100, 40, 5)
        c2 = st.slider("Code Style %", 0, 100, 20, 5)
        c3 = st.slider("Efficiency %", 0, 100, 20, 5)
        c4 = st.slider("Documentation %", 0, 100, 20, 5)
        total = c1 + c2 + c3 + c4
        if total != 100:
            st.error(f"Weights sum to {total}% — must be 100%")
        else:
            rubric = Rubric(
                name="Custom",
                criteria=[
                    RubricCriterion("Correctness", c1/100, "Correct output for all inputs"),
                    RubricCriterion("Code style", c2/100, "PEP8, naming, clean code"),
                    RubricCriterion("Efficiency", c3/100, "Appropriate algorithms"),
                    RubricCriterion("Documentation", c4/100, "Docstrings and comments"),
                ],
            )

    st.divider()
    st.subheader("Language")
    language = st.selectbox("Language", ["python", "javascript", "java"], index=0)

    st.divider()
    st.markdown("Built for **EdTech 3.0 Hackathon**\nTrack 2 · Assessment & Feedback")


# --- Main area ---
st.title("🔍 CodeReview AI")
st.caption("AI-powered code assignment reviewer for CS educators")

col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.subheader("📋 Assignment")
    assignment_title = st.text_input("Assignment title", placeholder="e.g. Bubble Sort Implementation")
    assignment_prompt = st.text_area(
        "Assignment prompt",
        placeholder="Describe what the student was asked to do...",
        height=120,
    )

    st.subheader("💻 Student Code")
    code = st.text_area(
        "Paste student code here",
        placeholder="def bubble_sort(arr):\n    ...",
        height=300,
        label_visibility="collapsed",
    )

    submitted = st.button("🚀 Review Code", type="primary", use_container_width=True)


with col2:
    st.subheader("📊 Feedback")

    if submitted:
        if not api_key:
            st.error("Please enter your Groq API key in the sidebar.")
        elif not code.strip():
            st.error("Please paste some code to review.")
        elif not assignment_prompt.strip():
            st.error("Please enter the assignment prompt.")
        elif rubric is None:
            st.error("Custom rubric weights must sum to 100%.")
        else:
            with st.spinner("Analyzing code..."):
                try:
                    reviewer = CodeReviewer(api_key=api_key)
                    result = reviewer.review(
                        code=code,
                        assignment_prompt=assignment_prompt,
                        rubric=rubric,
                        language=language,
                    )
                except Exception as e:
                    st.error(f"Error: {e}")
                    result = None

            if result and result.success:
                # Score + grade
                m1, m2, m3 = st.columns(3)
                m1.metric("Overall Score", f"{result.overall_score:.1f}/100")
                m2.metric("Grade", result.grade_letter)
                sa = result.static_analysis
                m3.metric("Static Issues", len(sa.issues) if sa else 0)

                # Grade badge
                grade_class = f"grade-{result.grade_letter[0]}"
                st.markdown(
                    f'<div class="grade-badge {grade_class}">{result.grade_letter}</div>',
                    unsafe_allow_html=True,
                )

                st.markdown(f"**Summary:** {result.summary}")

                st.divider()

                # Rubric breakdown
                st.subheader("📐 Rubric Breakdown")
                for cs in result.criteria_scores:
                    pct = (cs.score / 10) * 100
                    st.markdown(f"**{cs.name}** ({int(cs.weight*100)}%) — {cs.score:.1f}/10")
                    st.progress(pct / 100)
                    st.caption(cs.feedback)

                st.divider()

                # Line comments
                if result.line_comments:
                    st.subheader("📍 Line Comments")
                    for lc in result.line_comments:
                        css_class = f"comment-{lc.type}"
                        icon = {"error": "🔴", "warning": "🟡", "suggestion": "🔵", "praise": "🟢"}.get(lc.type, "⚪")
                        st.markdown(
                            f'<div class="{css_class}">{icon} <strong>Line {lc.line}</strong> — {lc.comment}</div>',
                            unsafe_allow_html=True,
                        )

                st.divider()

                # Strengths & improvements
                scol, icol = st.columns(2)
                with scol:
                    st.subheader("✅ Strengths")
                    for s in result.strengths:
                        st.markdown(f"- {s}")
                with icol:
                    st.subheader("🔧 Improvements")
                    for i in result.improvements:
                        st.markdown(f"- {i}")

            elif result:
                st.error(f"Review failed: {result.error}")

    else:
        st.info("Fill in the assignment details and paste the student's code, then click **Review Code**.")

        # Show example
        with st.expander("See an example"):
            st.markdown("**Assignment:** Implement bubble sort")
            st.code('''def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr''', language="python")
            st.markdown("→ CodeReview AI will score this against correctness, style, efficiency, and documentation.")