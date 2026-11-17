import calendar as pycal
import html as html_lib
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import icalendar
import recurring_ical_events
from pypdf import PdfReader
from docx import Document
from PIL import Image
from google import genai
from google.genai import types
from supabase import create_client
from streamlit_calendar import calendar
import streamlit as st

st.set_page_config(page_title="Semester Planner", layout="wide", initial_sidebar_state="expanded")

MODEL_ID = "gemini-3.8-flash"

# Initialize Supabase client
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def esc(text) -> str:
    return html_lib.escape(str(text)).replace("\n", " ").replace("\r", " ")

def render_html(raw_html: str):
    single_line = " ".join(line.strip() for line in raw_html.splitlines() if line.strip())
    st.markdown(single_line, unsafe_allow_html=True)

# ---------- Custom Bento Aesthetic CSS ----------
render_html("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', sans-serif;
}

.stApp {
    background-color: #F7F3EE;
    color: #3E313B;
}

section[data-testid="stSidebar"] {
    background-color: #E6E0DE;
    border-right: 1px solid #D8CFD1;
}

div[data-testid="stTextInput"] input {
    border-radius: 999px !important;
    background-color: #EDE7E5 !important;
    border: 1px solid #D5CBCD !important;
    padding-left: 18px !important;
    color: #3E313B !important;
}

button[kind="primary"], button[kind="secondary"], div[data-testid="stFormSubmitButton"] button {
    border-radius: 999px !important;
    font-weight: 600 !important;
}

.bento-card {
    background-color: #EBE4E6;
    border-radius: 22px;
    padding: 18px 20px;
    margin-bottom: 16px;
    box-shadow: 0 2px 10px rgba(62, 49, 59, 0.04);
}
.bento-title {
    font-size: 1.02rem;
    font-weight: 700;
    color: #4A3B47;
    margin-bottom: 12px;
}

.pill-row {
    background-color: #F7F3EE;
    border-radius: 999px;
    padding: 9px 16px;
    margin-bottom: 9px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-size: 0.88rem;
    color: #3E313B;
}
.pill-left {
    display: flex;
    align-items: center;
    gap: 10px;
    overflow: hidden;
    min-width: 0;
}
.pill-badge {
    background-color: #EBE4E6;
    color: #5C4958;
    font-weight: 700;
    font-size: 0.75rem;
    padding: 4px 10px;
    border-radius: 999px;
    white-space: nowrap;
}
.pill-title {
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.pill-sub {
    font-size: 0.76rem;
    color: #7D6B78;
    white-space: nowrap;
}

.date-circle {
    min-width: 34px;
    height: 34px;
    border-radius: 50%;
    background-color: #FFFFFF;
    color: #4A3B47;
    font-weight: 700;
    font-size: 0.85rem;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.plum-panel {
    background-color: #8D7588;
    border-radius: 26px;
    padding: 16px 14px;
    color: #FFFFFF;
}
.plum-subcard {
    background-color: #7B6376;
    border-radius: 20px;
    padding: 14px 10px;
    margin-bottom: 14px;
    text-align: center;
}
.plum-label {
    font-size: 0.85rem;
    font-weight: 600;
    color: #F5EFF3;
    margin-bottom: 8px;
}

.profile-box {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 4px 14px 4px;
}
.avatar-circle {
    width: 46px;
    height: 46px;
    border-radius: 50%;
    background: linear-gradient(135deg, #8D7588, #5A4556);
    color: #FFFFFF;
    font-weight: 700;
    font-size: 1.15rem;
    display: flex;
    align-items: center;
    justify-content: center;
}

.mini-cal {
    width: 100%;
    border-collapse: collapse;
    text-align: center;
    font-size: 0.78rem;
    color: #5A4A56;
    background: #F7F3EE;
    border-radius: 16px;
    overflow: hidden;
}
.mini-cal th {
    padding: 6px 2px;
    font-weight: 700;
    color: #8D7588;
}
.mini-cal td {
    padding: 5px 2px;
}
.cal-today {
    background-color: #8D7588;
    color: #FFFFFF !important;
    border-radius: 50%;
    font-weight: 700;
    display: inline-block;
    width: 22px;
    height: 22px;
    line-height: 22px;
}
.cal-due {
    border: 1.5px solid #D9777F;
    border-radius: 50%;
    font-weight: 700;
    display: inline-block;
    width: 22px;
    height: 22px;
    line-height: 20px;
}
</style>
""")

# ---------- Authentication Gate ----------
if "user" not in st.session_state:
    st.session_state["user"] = None
if "session" not in st.session_state:
    st.session_state["session"] = None

if st.session_state["session"] is not None:
    supabase.auth.set_session(
        st.session_state["session"].access_token,
        st.session_state["session"].refresh_token,
    )

if st.session_state["user"] is None:
    st.title("Semester Planner")
    st.subheader("Sign in or create an account to manage your semester workload")

    tab_login, tab_signup = st.tabs(["Log In", "Sign Up"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log In"):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state["user"] = res.user
                    st.session_state["session"] = res.session
                    st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")

    with tab_signup:
        with st.form("signup_form"):
            full_name = st.text_input("Your First Name (e.g., Kaya)")
            new_email = st.text_input("Email")
            new_password = st.text_input("Password (min 6 characters)", type="password")
            if st.form_submit_button("Create Account"):
                try:
                    res = supabase.auth.sign_up({
                        "email": new_email,
                        "password": new_password,
                        "options": {"data": {"full_name": full_name.strip()}},
                    })
                    if res.user:
                        st.session_state["user"] = res.user
                        st.session_state["session"] = res.session
                        st.rerun()
                except Exception as e:
                    st.error(f"Sign up failed: {e}")

    st.stop()

# ---------- User Profile & Preferences ----------
user = st.session_state["user"]
user_id = user.id
meta = user.user_metadata or {}
display_name = meta.get("full_name") or user.email.split("@")[0].capitalize()
initials = "".join(part[0].upper() for part in display_name.split()[:2]) or "S"

daily_capacity = float(meta.get("daily_capacity", 6.0))
exam_spread = int(meta.get("exam_spread", 7))
assign_spread = int(meta.get("assign_spread", 4))

def get_greeting(name: str) -> str:
    now_local = datetime.now(ZoneInfo("America/New_York"))
    hour = now_local.hour
    if hour < 12:
        period = "Good Morning"
    elif hour < 17:
        period = "Good Afternoon"
    else:
        period = "Good Evening"
    return f"{period}, {name}"

def render_progress_ring(label: str, pct: int, stroke_color: str) -> str:
    pct = max(0, min(100, int(pct)))
    radius = 34
    circumference = 2 * 3.14159 * radius
    offset = circumference * (1 - pct / 100.0)
    return (
        f'<div class="plum-subcard">'
        f'<div class="plum-label">{esc(label)}</div>'
        f'<svg width="88" height="88" viewBox="0 0 88 88">'
        f'<circle cx="44" cy="44" r="{radius}" fill="none" stroke="rgba(255,255,255,0.18)" stroke-width="7" />'
        f'<circle cx="44" cy="44" r="{radius}" fill="none" stroke="{stroke_color}" stroke-width="7" '
        f'stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{offset:.1f}" '
        f'stroke-linecap="round" transform="rotate(-90 44 44)" />'
        f'<text x="44" y="49" text-anchor="middle" fill="#FFFFFF" font-size="16" font-weight="700">{pct}%</text>'
        f'</svg></div>'
    )

def render_mini_calendar(year: int, month: int, today_day: int, due_days: set[int]) -> str:
    cal_matrix = pycal.monthcalendar(year, month)
    month_name = datetime(year, month, 1).strftime("%B %Y")
    parts = [
        f'<div style="text-align:center; font-weight:700; font-size:0.85rem; color:#4A3B47; margin-bottom:6px;">{month_name}</div>',
        '<table class="mini-cal"><tr><th>Mo</th><th>Tu</th><th>We</th><th>Th</th><th>Fr</th><th>Sa</th><th>Su</th></tr>',
    ]
    for week in cal_matrix:
        parts.append("<tr>")
        for d in week:
            if d == 0:
                parts.append("<td></td>")
            elif d == today_day:
                parts.append(f'<td><span class="cal-today">{d}</span></td>')
            elif d in due_days:
                parts.append(f'<td><span class="cal-due">{d}</span></td>')
            else:
                parts.append(f"<td>{d}</td>")
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)

# ---------- Database & AI Helpers ----------
def load_user_df() -> pd.DataFrame:
    res = supabase.table("items").select("*").eq("user_id", user_id).execute()
    if not res.data:
        return pd.DataFrame(columns=["id", "course", "date", "title", "type", "hours", "difficulty", "done"])
    df = pd.DataFrame(res.data)
    if "course" not in df.columns:
        df["course"] = "General"
    df["course"] = df["course"].fillna("General").replace("", "General")
    df["date"] = pd.to_datetime(df["date"])
    df["hours"] = df["hours"].astype(float)
    df["difficulty"] = df["difficulty"].astype(int)
    return df

def add_rows_dedup(new_rows: list[dict]) -> int:
    if not new_rows:
        return 0
    existing = load_user_df()
    existing_keys = set()
    if not existing.empty:
        existing_keys = set(
            zip(existing["date"].dt.strftime("%Y-%m-%d"), existing["title"].str.strip().str.lower())
        )

    unique_rows = []
    for row in new_rows:
        clean_title = str(row.get("title", "Untitled")).strip().replace(",", " ")
        date_str = str(row.get("date"))[:10]
        key = (date_str, clean_title.lower())
        if key not in existing_keys:
            existing_keys.add(key)
            unique_rows.append({
                "user_id": user_id,
                "course": str(row.get("course") or "General").strip() or "General",
                "date": date_str,
                "title": clean_title,
                "type": row.get("type", "assignment"),
                "hours": float(row.get("hours", 1.5)),
                "difficulty": int(row.get("difficulty", 3)),
                "done": row.get("done", "no"),
            })

    if unique_rows:
        supabase.table("items").insert(unique_rows).execute()
    return len(unique_rows)

def detect_course_code(text: str) -> str:
    if not text:
        return "General"
    # Matches patterns like MATH-2167, ITSC 3155, 202680-MATH-2167-001, CHEM1251L
    match = re.search(r"(?<![A-Za-z])([A-Za-z]{2,5})[\s_-]?(\d{3,4}[A-Za-z]?)(?![0-9])", text)
    if match:
        dept = match.group(1).upper()
        # Ignore common non-course words that precede numbers (e.g., Quiz 3, Exam 2, Lab 1, Test 3)
        if dept not in {"QUIZ", "EXAM", "TEST", "LAB", "HW", "PART", "WEEK", "UNIT", "MOD", "CH", "PAGE"}:
            return f"{dept} {match.group(2).upper()}"
    return "General"

def clean_canvas_title(raw_summary: str) -> str:
    # Removes trailing/embedded Canvas bracket tags like [202680-MATH-2167-001-13789] for cleaner display
    cleaned = re.sub(r"\[[^\]]*[A-Za-z]{2,5}[\s_-]?\d{3,4}[^\]]*\]", "", raw_summary).strip()
    return cleaned if cleaned else raw_summary.strip()

def parse_ics_url(ics_url: str) -> list[dict]:
    resp = requests.get(ics_url.strip(), timeout=15)
    resp.raise_for_status()
    cal = icalendar.Calendar.from_ical(resp.content)

    start_window = datetime.now() - timedelta(days=7)
    end_window = datetime.now() + timedelta(days=120)
    events = recurring_ical_events.of(cal).between(start_window, end_window)

    rows = []
    for event in events:
        raw_summary = str(event.get("SUMMARY", "Calendar Event")).replace(",", " ")
        raw_desc = str(event.get("DESCRIPTION", ""))
        raw_cats = str(event.get("CATEGORIES", ""))

        dtstart = event.get("DTSTART").dt
        dtend = event.get("DTEND").dt if event.get("DTEND") else dtstart
        duration_hrs = round(max((dtend - dtstart).total_seconds() / 3600, 0.5), 2) if hasattr(dtstart, "hour") else 2.0

        # Check summary first, then Canvas description/categories for the course code
        course = detect_course_code(raw_summary)
        if course == "General":
            course = detect_course_code(raw_desc)
        if course == "General":
            course = detect_course_code(raw_cats)

        clean_title = clean_canvas_title(raw_summary)
        lower = raw_summary.lower()
        if any(w in lower for w in ["exam", "midterm", "final", "test", "quiz"]):
            item_type, diff = "exam", 5
        elif any(w in lower for w in ["homework", "hw", "project", "lab", "assignment", "paper"]):
            item_type, diff = "assignment", 3
        else:
            item_type, diff = "recurring", 2

        rows.append({
            "course": course,
            "date": dtstart.strftime("%Y-%m-%d"),
            "title": clean_title,
            "type": item_type,
            "hours": duration_hrs,
            "difficulty": diff,
            "done": "no",
        })
    return rows

def parse_quick_natural_language(text: str) -> list[dict]:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    today_str = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d (%A)")
    prompt = f"""
    Today is {today_str}. Convert this student's natural-language note into a JSON array of 1 or more schedule items.
    Return ONLY valid JSON with these exact keys:
    - "course": inferred course code (e.g., "ITSC 3155", "Work", or "General")
    - "date": "YYYY-MM-DD" resolved relative to today
    - "title": clean task/event title
    - "type": one of "exam", "assignment", "quiz", "reading", "recurring", "job"
    - "hours": estimated hours (number, default 1.5 if unstated)
    - "difficulty": integer 1 to 5 (default 3 if unstated)
    - "done": "no"

    Input: "{text}"
    """
    res = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=0)),
    )
    raw = res.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)

def parse_syllabus_multimodal(uploaded_file=None, pasted_text: str = "", default_course: str = "") -> list[dict]:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    contents = []
    prompt = f"""
    Extract all graded assignments, quizzes, labs, projects, and exams with due dates from this syllabus.
    Return ONLY a valid JSON array of objects with these exact keys:
    - "course": course code/name (use "{default_course}" if provided, otherwise infer from syllabus, or "General")
    - "date": "YYYY-MM-DD" (use 2026 if year is omitted)
    - "title": string without commas
    - "type": one of "exam", "assignment", "quiz", "reading"
    - "hours": estimated study/work hours (number, e.g., 1.5, 3, 6)
    - "difficulty": integer from 1 to 5
    - "done": "no"
    """
    contents.append(prompt)

    if uploaded_file is not None:
        fname = uploaded_file.name.lower()
        if fname.endswith(".pdf"):
            reader = PdfReader(uploaded_file)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            contents.append(text[:18000])
        elif fname.endswith(".docx"):
            doc = Document(uploaded_file)
            text = "\n".join(p.text for p in doc.paragraphs)
            for table in doc.tables:
                for row in table.rows:
                    text += "\n" + " | ".join(cell.text.strip() for cell in row.cells)
            contents.append(text[:18000])
        elif fname.endswith((".png", ".jpg", ".jpeg", ".webp")):
            img = Image.open(uploaded_file)
            contents.append(img)

    if pasted_text.strip():
        contents.append(pasted_text.strip()[:18000])

    response = client.models.generate_content(
        model=MODEL_ID,
        contents=contents,
        config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=0)),
    )
    raw = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)

def stream_study_plan(df: pd.DataFrame, load_df: pd.DataFrame):
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    today = pd.Timestamp.now().normalize()
    upcoming_items = df[(df["done"] == "no") & (df["date"] >= today) & (df["date"] <= today + pd.Timedelta(days=14))]
    peak_days = load_df[(load_df["date"] >= today) & (load_df["date"] <= today + pd.Timedelta(days=14)) & (load_df["intensity"] >= 6.0)]

    items_summary = upcoming_items[["course", "date", "title", "type", "hours", "difficulty"]].to_dict(orient="records")
    peaks_summary = peak_days[["date", "intensity"]].to_dict(orient="records")

    prompt = f"""
    You are an academic coach for {display_name}. Today is {today.strftime('%Y-%m-%d')}.
    Daily capacity: {daily_capacity}h/day.
    Peak days (0-10): {peaks_summary}
    Tasks (next 14 days): {items_summary}

    Write a concise, bulleted 7-day study plan to flatten peak crunch days. Name exact courses, tasks, and realistic hour blocks within {daily_capacity}h/day. Keep it brief and scannable.
    """
    response = client.models.generate_content_stream(
        model=MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            max_output_tokens=700,
        ),
    )
    for chunk in response:
        if chunk.text:
            yield chunk.text

# ---------- Left Taupe Sidebar Navigation & Importers ----------
with st.sidebar:
    render_html(
        f'<div style="font-size:1.35rem; font-weight:800; color:#4A3B47; letter-spacing:-0.5px; margin-bottom:4px;">'
        f'Plan<span style="color:#8D7588;">tech</span></div>'
        f'<div class="profile-box"><div class="avatar-circle">{esc(initials)}</div>'
        f'<div><div style="font-weight:700; color:#3E313B; font-size:0.95rem;">{esc(display_name)}</div>'
        f'<div style="font-size:0.75rem; color:#7D6B78;">{esc(user.email)}</div></div></div>'
    )

    nav_page = st.radio(
        "Navigation",
        ["Dashboard", "Workload Forecast", "Full Calendar", "Master Task Editor", "AI Study Coach"],
        label_visibility="collapsed",
    )

    st.divider()

    with st.expander("Import Calendar (.ics)"):
        ics_link = st.text_input("Paste secret .ics URL", placeholder="https://...")
        if st.button("Sync Calendar") and ics_link:
            try:
                imported = parse_ics_url(ics_link)
                added_count = add_rows_dedup(imported)
                st.success(f"Added {added_count} new events!")
                st.rerun()
            except Exception as e:
                st.error(f"Sync failed: {e}")
        if st.button("Auto-Tag Existing 'General' Items"):
            existing_gen = supabase.table("items").select("*").eq("user_id", user_id).eq("course", "General").execute().data
            updated = 0
            for item in existing_gen:
                detected = detect_course_code(item["title"])
                if detected != "General":
                    supabase.table("items").update({
                        "course": detected,
                        "title": clean_canvas_title(item["title"]),
                 }).eq("id", item["id"]).execute()
                updated += 1
        st.success(f"Organized {updated} items into their courses!")
        st.rerun()
    with st.expander("AI Syllabus Extractor"):
        course_tag = st.text_input("Course Tag (optional)", placeholder="e.g., ITSC 3155")
        syl_file = st.file_uploader("PDF, Word (.docx), or Image", type=["pdf", "docx", "png", "jpg", "jpeg"])
        syl_text = st.text_area("Or paste syllabus text", height=80)
        if st.button("Extract Deadlines") and (syl_file is not None or syl_text.strip()):
            try:
                extracted = parse_syllabus_multimodal(syl_file, syl_text, course_tag)
                added_count = add_rows_dedup(extracted)
                st.success(f"Added {added_count} new items!")
                st.rerun()
            except Exception as e:
                st.error(f"Extraction failed: {e}")

    with st.expander("Add Item Manually"):
        with st.form("add_item_form", clear_on_submit=True):
            m_course = st.text_input("Course", value="General")
            m_title = st.text_input("Title")
            m_date = st.date_input("Date")
            m_type = st.selectbox("Type", ["assignment", "exam", "quiz", "reading", "recurring", "job"])
            m_hours = st.number_input("Hours", min_value=0.25, max_value=40.0, value=1.5, step=0.25)
            m_diff = st.slider("Difficulty", 1, 5, 3)
            if st.form_submit_button("Add Item") and m_title.strip():
                add_rows_dedup([{
                    "course": m_course.strip() or "General",
                    "date": m_date.strftime("%Y-%m-%d"),
                    "title": m_title.strip(),
                    "type": m_type,
                    "hours": m_hours,
                    "difficulty": m_diff,
                    "done": "no",
                }])
                st.rerun()

    with st.expander("Settings & Calibration"):
        updated_name = st.text_input("Display Name", value=display_name)
        new_cap = st.slider("Daily Study Capacity (hrs)", 2.0, 14.0, daily_capacity, 0.5)
        new_exam_sp = st.slider("Exam Prep Spread (days)", 2, 14, exam_spread)
        new_assign_sp = st.slider("Assignment Spread (days)", 1, 10, assign_spread)
        if st.button("Save Settings"):
            res = supabase.auth.update_user({
                "data": {
                    "full_name": updated_name.strip() or display_name,
                    "daily_capacity": new_cap,
                    "exam_spread": new_exam_sp,
                    "assign_spread": new_assign_sp,
                }
            })
            st.session_state["user"] = res.user
            st.rerun()

    st.divider()
    if st.button("Log Out", use_container_width=True):
        supabase.auth.sign_out()
        st.session_state["user"] = None
        st.session_state["session"] = None
        st.rerun()

# ---------- Load Data & Top Header Row ----------
df = load_user_df()
now_ny = datetime.now(ZoneInfo("America/New_York"))
today_local = pd.Timestamp(now_ny.date())

top_left, top_right = st.columns([2.2, 1.5])
with top_left:
    render_html(f"<h1 style='margin-bottom:0; color:#3E313B; font-weight:800;'>{esc(get_greeting(display_name))}</h1>")
    if not df.empty:
        due_today = df[(df["done"] == "no") & (df["date"].dt.normalize() == today_local)]
        if due_today.empty:
            next_up = df[(df["done"] == "no") & (df["date"].dt.normalize() > today_local)].sort_values("date")
            if next_up.empty:
                st.caption("You have nothing due today and no upcoming deadlines.")
            else:
                nxt = next_up.iloc[0]
                st.caption(f"Nothing due today. Next up: **{nxt['title']}** ({nxt['course']}) on {nxt['date'].strftime('%b %d')}.")
        elif len(due_today) == 1:
            item = due_today.iloc[0]
            st.caption(f"You have **{item['title']}** ({item['course']}) due today ({item['hours']}h).")
        else:
            top_item = due_today.sort_values(["difficulty", "hours"], ascending=False).iloc[0]["title"]
            others = len(due_today) - 1
            st.caption(f"You have **{top_item}** and {others} other {'item' if others == 1 else 'items'} due today.")

with top_right:
    with st.form("quick_nl_form", clear_on_submit=True):
        q1, q2 = st.columns([3.5, 1.3])
        nl_prompt = q1.text_input(
            "AI Quick-Add",
            placeholder="✨ Quick-Add: 'CS 3155 Quiz Friday 2h'",
            label_visibility="collapsed",
        )
        if q2.form_submit_button("Add", use_container_width=True) and nl_prompt.strip():
            try:
                parsed = parse_quick_natural_language(nl_prompt.strip())
                add_rows_dedup(parsed)
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
    st.caption("AI Quick-Add: creates tasks from plain English")

if df.empty:
    st.info("Your schedule is empty! Use the AI Quick-Add bar above or the left sidebar to import Canvas/Google Calendar or upload a syllabus.")
    st.stop()

# Course Filter Pills
all_courses = sorted(df["course"].unique().tolist())
selected_courses = st.multiselect("Active Courses", options=all_courses, default=all_courses, label_visibility="collapsed")
filtered_df = df[df["course"].isin(selected_courses)].copy()

if filtered_df.empty:
    st.warning("Select at least one course above.")
    st.stop()

# ---------- Compute Workload & Completion Metrics ----------
filtered_df["effort"] = filtered_df["hours"] * (0.5 + filtered_df["difficulty"] * 0.25)
SPREAD_DAYS = {"exam": exam_spread, "assignment": assign_spread}
daily_records = []

for _, row in filtered_df.iterrows():
    spread = SPREAD_DAYS.get(row["type"], 1)
    weights = np.arange(1, spread + 1, dtype=float)
    weights /= weights.sum()
    for offset, w in enumerate(reversed(weights)):
        day = row["date"] - pd.Timedelta(days=offset)
        daily_records.append({
            "date": day.normalize(),
            "course": row["course"],
            "load": row["effort"] * w,
        })

raw_daily = pd.DataFrame(daily_records)
load_df = raw_daily.groupby("date", as_index=False)["load"].sum()
full_range = pd.date_range(load_df["date"].min(), load_df["date"].max(), freq="D")
load_df = load_df.set_index("date").reindex(full_range, fill_value=0.0).rename_axis("date").reset_index()

max_reference_effort = daily_capacity * 1.5
load_df["intensity"] = (load_df["load"] / max_reference_effort * 10).clip(0, 10).round(1)
peak_threshold = min(round(load_df["intensity"].mean() + load_df["intensity"].std(), 1), 9.5)
load_df["color"] = load_df["intensity"].apply(lambda v: "#D96B78" if v >= 6.5 else ("#E5A93B" if v >= 3.0 else "#5BB396"))

total_items = len(filtered_df)
done_items = int((filtered_df["done"] == "yes").sum())
overall_pct = round((done_items / total_items) * 100) if total_items else 0

course_stats = []
for c_name in selected_courses:
    c_sub = filtered_df[filtered_df["course"] == c_name]
    c_pct = round(((c_sub["done"] == "yes").sum() / len(c_sub)) * 100) if len(c_sub) else 0
    course_stats.append((c_name, c_pct))

# ---------- Page Views ----------
if nav_page == "Dashboard":
    main_area, right_rail = st.columns([3.3, 1.0])

    with main_area:
        b1, b2 = st.columns(2)

        with b1:
            urgent = filtered_df[
                (filtered_df["done"] == "no") & (filtered_df["date"] >= today_local)
            ].sort_values(["difficulty", "date"], ascending=[False, True]).head(3)

            if urgent.empty:
                rows_html = '<div class="pill-row"><span class="pill-sub">All caught up on urgent tasks!</span></div>'
            else:
                rows_html = "".join(
                    f'<div class="pill-row"><div class="pill-left"><span class="pill-badge">{esc(r["course"])}</span><span class="pill-title">{esc(r["title"])}</span></div><span class="pill-sub">Diff {int(r["difficulty"])}/5</span></div>'
                    for _, r in urgent.iterrows()
                )
            render_html(f'<div class="bento-card"><div class="bento-title">Priority Focus</div>{rows_html}</div>')

        with b2:
            upcoming = filtered_df[
                (filtered_df["done"] == "no") & (filtered_df["date"] >= today_local)
            ].sort_values("date").head(3)

            if upcoming.empty:
                up_html = '<div class="pill-row"><span class="pill-sub">No upcoming deadlines scheduled.</span></div>'
            else:
                up_html = "".join(
                    f'<div class="pill-row"><div class="pill-left"><span class="pill-badge">{r["date"].strftime("%b %d")}</span><span class="pill-title">{esc(r["title"])}</span></div><span class="pill-sub">{r["hours"]}h</span></div>'
                    for _, r in upcoming.iterrows()
                )
            render_html(f'<div class="bento-card"><div class="bento-title">Upcoming Events</div>{up_html}</div>')

        month_due = filtered_df[
            (filtered_df["date"].dt.year == now_ny.year) & (filtered_df["date"].dt.month == now_ny.month)
        ]
        due_day_nums = set(month_due["date"].dt.day.tolist())
        cal_html = render_mini_calendar(now_ny.year, now_ny.month, now_ny.day, due_day_nums)

        next_three = filtered_df[filtered_df["date"] >= today_local].sort_values("date").head(3)
        if next_three.empty:
            sched_pills = '<div class="pill-row"><span class="pill-sub">No events left this week.</span></div>'
        else:
            sched_pills = "".join(
                f'<div class="pill-row"><div class="pill-left"><div class="date-circle">{r["date"].day}</div><div><div class="pill-title">{esc(r["title"])}</div><div class="pill-sub">{esc(r["course"])} • {esc(r["type"]).capitalize()}</div></div></div><span class="pill-sub">{r["hours"]}h</span></div>'
                for _, r in next_three.iterrows()
            )

        render_html(
            f'<div class="bento-card"><div class="bento-title">My Schedule</div>'
            f'<div style="display:grid; grid-template-columns: 1.05fr 1.35fr; gap:16px; align-items:center;">'
            f'<div>{cal_html}</div><div>{sched_pills}</div></div></div>'
        )

        render_html('<div class="bento-card" style="padding-bottom:10px;"><div class="bento-title" style="margin-bottom:0;">Workload Intensity Forecast (0 = Free, 10 = Heavy Crunch)</div></div>')
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=load_df["date"],
            y=load_df["intensity"],
            mode="lines+markers",
            line=dict(color="#8D7588", width=3, shape="spline", smoothing=0.4),
            fill="tozeroy",
            fillcolor="rgba(141, 117, 136, 0.16)",
            marker=dict(color=load_df["color"], size=7, line=dict(width=1, color="white")),
            hovertemplate="<b>%{x|%b %d}</b> • Intensity: <b>%{y}/10</b><extra></extra>",
        ))
        fig.add_hline(y=peak_threshold, line_dash="dash", line_color="#D96B78")
        fig.update_layout(
            paper_bgcolor="#EBE4E6",
            plot_bgcolor="#F7F3EE",
            yaxis=dict(range=[-0.4, 10.5], tickvals=[0, 5, 10], ticktext=["0 (Free)", "5", "10 (Max)"], gridcolor="#DFD6D8"),
            xaxis=dict(showgrid=False),
            height=230,
            margin=dict(l=14, r=14, t=14, b=14),
        )
        st.plotly_chart(fig, use_container_width=True)

    with right_rail:
        ring_colors = ["#EB7A88", "#65C3BA", "#F0B95B", "#9CC5E9"]
        rings_html = render_progress_ring("Overall Coursework", overall_pct, ring_colors[0])
        for idx, (c_name, c_pct) in enumerate(course_stats):
            rings_html += render_progress_ring(c_name, c_pct, ring_colors[(idx + 1) % len(ring_colors)])

        render_html(
            f'<div class="plum-panel">{rings_html}'
            f'<div style="text-align:center; font-size:0.82rem; font-weight:600; color:#F5EFF3; padding-top:4px;">'
            f'{done_items} of {total_items} tasks done</div></div>'
        )

elif nav_page == "Workload Forecast":
    st.subheader("Semester Workload Forecast")
    chart_mode = st.radio("View Mode", ["Total Intensity Line", "Stacked by Course"], horizontal=True)
    with st.expander(f"Workload Scale Guide (0–10, calibrated to {daily_capacity}h/day)"):
        st.markdown("- **0–2.9 (Green):** Free / Light\n- **3.0–6.4 (Yellow):** Moderate\n- **6.5–10.0 (Red):** Heavy Crunch")

    if chart_mode == "Total Intensity Line":
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=load_df["date"], y=load_df["intensity"], mode="lines+markers",
            line=dict(color="#8D7588", width=3, shape="spline", smoothing=0.4),
            fill="tozeroy", fillcolor="rgba(141, 117, 136, 0.16)",
            marker=dict(color=load_df["color"], size=8, line=dict(width=1, color="white")),
            hovertemplate="<b>%{x|%b %d, %Y}</b><br>Intensity: <b>%{y}/10</b><extra></extra>",
        ))
        fig.add_hline(y=peak_threshold, line_dash="dash", line_color="#D96B78", annotation_text=f"Peak ({peak_threshold}/10)")
        fig.update_layout(
            paper_bgcolor="#EBE4E6", plot_bgcolor="#F7F3EE",
            xaxis=dict(rangeslider=dict(visible=True), type="date"),
            yaxis=dict(title="Workload Intensity (0–10)", range=[-0.4, 10.6], tickvals=[0, 2.5, 5, 7.5, 10], ticktext=["0 (Free)", "2.5", "5 (Moderate)", "7.5", "10 (Max)"]),
            height=430,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        course_daily = raw_daily.groupby(["date", "course"], as_index=False)["load"].sum()
        course_daily["intensity"] = (course_daily["load"] / max_reference_effort * 10).clip(0, 10).round(2)
        fig_stack = px.area(course_daily, x="date", y="intensity", color="course")
        fig_stack.update_layout(paper_bgcolor="#EBE4E6", plot_bgcolor="#F7F3EE", yaxis=dict(range=[0, 10.6]), height=430)
        st.plotly_chart(fig_stack, use_container_width=True)

elif nav_page == "Full Calendar":
    st.subheader("Interactive Semester Calendar")
    cal_events = []
    for _, r in filtered_df.iterrows():
        bg = "#9ca3af" if r["done"] == "yes" else ("#D96B78" if r["difficulty"] >= 4 else ("#E5A93B" if r["difficulty"] == 3 else "#5BB396"))
        cal_events.append({
            "title": f"[{r['course']}] {r['title']} ({r['hours']}h)",
            "start": r["date"].strftime("%Y-%m-%d"),
            "end": r["date"].strftime("%Y-%m-%d"),
            "backgroundColor": bg,
            "borderColor": bg,
        })
    calendar(
        events=cal_events,
        options={"initialView": "dayGridMonth", "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,listWeek"}, "height": 620},
        key="full_cal_grid",
    )

elif nav_page == "Master Task Editor":
    st.subheader("Check Off, Edit, or Delete Tasks")
    st.caption("Checking off tasks here immediately updates your circular completion rings on the Dashboard.")
    edit_df = filtered_df[["id", "done", "course", "date", "title", "type", "hours", "difficulty"]].sort_values("date").copy()
    edit_df["done"] = edit_df["done"] == "yes"
    edit_df["date"] = edit_df["date"].dt.date
    edit_df["Delete"] = False

    edited = st.data_editor(
        edit_df, hide_index=True, use_container_width=True, disabled=["id"],
        column_config={
            "id": None,
            "done": st.column_config.CheckboxColumn("Done", width="small"),
            "course": st.column_config.TextColumn("Course", width="small"),
            "date": st.column_config.DateColumn("Due Date", width="small"),
            "title": st.column_config.TextColumn("Title", width="large"),
            "type": st.column_config.SelectboxColumn("Type", options=["assignment", "exam", "quiz", "reading", "recurring", "job"], width="small"),
            "hours": st.column_config.NumberColumn("Hours", min_value=0.25, max_value=40.0, step=0.25, width="small"),
            "difficulty": st.column_config.NumberColumn("Diff", min_value=1, max_value=5, step=1, width="small"),
            "Delete": st.column_config.CheckboxColumn("Delete?", width="small"),
        },
        key="master_editor",
    )

    if st.button("Save Changes", type="primary"):
        orig_by_id = edit_df.set_index("id").to_dict(orient="index")
        for _, row in edited.iterrows():
            rid = int(row["id"])
            if row["Delete"]:
                supabase.table("items").delete().eq("id", rid).execute()
                continue
            orig = orig_by_id.get(rid, {})
            if (
                row["done"] != orig.get("done") or row["course"] != orig.get("course")
                or str(row["date"]) != str(orig.get("date")) or row["title"] != orig.get("title")
                or row["type"] != orig.get("type") or float(row["hours"]) != float(orig.get("hours"))
                or int(row["difficulty"]) != int(orig.get("difficulty"))
            ):
                supabase.table("items").update({
                    "done": "yes" if row["done"] else "no",
                    "course": str(row["course"]).strip() or "General",
                    "date": str(row["date"]),
                    "title": str(row["title"]).strip(),
                    "type": row["type"],
                    "hours": float(row["hours"]),
                    "difficulty": int(row["difficulty"]),
                }).eq("id", rid).execute()
        st.success("Saved!")
        st.rerun()

elif nav_page == "AI Study Coach":
    st.subheader("AI Crunch-Week Study Plan Generator")
    st.write(f"Generates a streaming 7-day plan calibrated to your **{daily_capacity}h/day** study capacity.")
    if st.button("Generate My 7-Day Study Plan", type="primary"):
        try:
            plan_text = st.write_stream(stream_study_plan(filtered_df, load_df))
            st.session_state["cached_study_plan"] = plan_text
        except Exception as e:
            st.error(f"Could not generate study plan: {e}")
    elif "cached_study_plan" in st.session_state:
        st.markdown(st.session_state["cached_study_plan"])