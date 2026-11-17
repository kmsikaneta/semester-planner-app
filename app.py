import calendar as pycal
import html as html_lib
import json
import re
import time
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

import busyness as bz

CHART_FONT = "Plus Jakarta Sans, -apple-system, Segoe UI, Helvetica, Arial, sans-serif"

st.set_page_config(page_title="Semester Planner", layout="wide", initial_sidebar_state="expanded")

MODEL_FALLBACKS = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash"]

# Initialize Supabase client
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def esc(text) -> str:
    return html_lib.escape(str(text)).replace("\n", " ").replace("\r", " ")

def render_html(raw_html: str):
    single_line = " ".join(line.strip() for line in raw_html.splitlines() if line.strip())
    st.markdown(single_line, unsafe_allow_html=True)

# ---------- Design System CSS (matches tokens.css from the design system) ----------
render_html("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600..800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

:root {
    --bg: #F7F6F3; --surface: #FFFFFF; --surface-sunken: #F0EEEA; --line: #E6E3DD;
    --ink: #15171C; --ink-2: #464B57; --ink-3: #686D7A;
    --font-display: "Bricolage Grotesque", "Plus Jakarta Sans", system-ui, sans-serif;
    --font-sans: "Plus Jakarta Sans", system-ui, sans-serif;
    --shadow-card: 0 1px 2px rgba(21,23,28,0.05), 0 6px 20px rgba(21,23,28,0.05);
}

html, body, [class*="css"] {
    font-family: var(--font-sans);
}
h1, h2, h3, .bento-title, .hero-title, .display {
    font-family: var(--font-display) !important;
    letter-spacing: -0.02em;
}

.stApp {
    background-color: var(--bg);
    color: var(--ink);
}

section[data-testid="stSidebar"] {
    background-color: var(--surface-sunken);
    border-right: 1px solid var(--line);
}

div[data-testid="stTextInput"] input {
    border-radius: 999px !important;
    background-color: var(--surface) !important;
    border: 1px solid var(--line) !important;
    padding-left: 18px !important;
    color: var(--ink) !important;
}

button[kind="primary"], button[kind="secondary"], div[data-testid="stFormSubmitButton"] button {
    border-radius: 999px !important;
    font-weight: 600 !important;
}

/* The hero: the semester graph on its own light stage */
.st-key-hero {
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: 28px;
    padding: 22px 26px 10px 26px;
    box-shadow: var(--shadow-card);
    margin-bottom: 8px;
}
.hero-head {
    display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap;
}
.hero-title {
    font-size: 1.7rem; font-weight: 800; color: var(--ink); line-height: 1.1;
}
.hero-sub {
    font-size: 0.95rem; color: var(--ink-2); margin-top: 6px;
}
.hero-sub b { color: var(--ink); }
.legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 0.78rem; color: var(--ink-3); font-weight: 600; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }

.bento-card {
    background-color: var(--surface);
    border: 1px solid var(--line);
    border-radius: 20px;
    padding: 18px 20px;
    margin-bottom: 16px;
    box-shadow: var(--shadow-card);
}
.bento-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--ink);
    margin-bottom: 12px;
}

.pill-row {
    background-color: var(--surface-sunken);
    border-radius: 999px;
    padding: 9px 16px;
    margin-bottom: 9px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-size: 0.88rem;
    color: var(--ink);
}
.pill-left {
    display: flex;
    align-items: center;
    gap: 10px;
    overflow: hidden;
    min-width: 0;
}
.pill-badge {
    background-color: var(--surface);
    border: 1px solid var(--line);
    color: var(--ink-2);
    font-weight: 700;
    font-size: 0.75rem;
    padding: 3px 10px;
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
    color: var(--ink-3);
    white-space: nowrap;
}

.date-circle {
    min-width: 34px;
    height: 34px;
    border-radius: 50%;
    background-color: var(--surface);
    color: var(--ink);
    font-weight: 700;
    font-size: 0.85rem;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    box-sizing: border-box;
}

.plum-panel {
    background-color: var(--surface);
    border: 1px solid var(--line);
    border-radius: 24px;
    padding: 16px 14px;
    color: var(--ink);
    box-shadow: var(--shadow-card);
}
.plum-subcard {
    background-color: var(--surface-sunken);
    border-radius: 18px;
    padding: 14px 10px;
    margin-bottom: 12px;
    text-align: center;
}
.plum-label {
    font-size: 0.85rem;
    font-weight: 700;
    color: var(--ink-2);
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
    background: var(--ink);
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
    color: var(--ink-2);
    background: var(--surface-sunken);
    border-radius: 16px;
    overflow: hidden;
}
.mini-cal th {
    padding: 6px 2px;
    font-weight: 700;
    color: var(--ink-3);
}
.mini-cal td {
    padding: 5px 2px;
}
.cal-today {
    background-color: var(--ink);
    color: #FFFFFF !important;
    border-radius: 50%;
    font-weight: 700;
    display: inline-block;
    width: 22px;
    height: 22px;
    line-height: 22px;
}
.cal-due {
    border-radius: 50%;
    font-weight: 700;
    display: inline-block;
    width: 22px;
    height: 22px;
    line-height: 22px;
}


.course-chip {
    display: inline-block;
    font-size: 0.78rem;
    font-weight: 700;
    padding: 5px 13px;
    border-radius: 999px;
    white-space: nowrap;
}
.chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 4px 0 16px 0;
}
.course-dot {
    width: 10px;
    height: 10px;
    min-width: 10px;
    border-radius: 50%;
    display: inline-block;
}
.progress-track {
    display: flex;
    height: 14px;
    border-radius: 999px;
    background-color: #DFD6D8;
    overflow: hidden;
    margin: 6px 0 14px 0;
}
.progress-seg {
    height: 100%;
}
.stat-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 10px;
}
.stat-box {
    background-color: #F7F3EE;
    border-radius: 16px;
    padding: 10px 14px;
}
.stat-num {
    font-size: 1.2rem;
    font-weight: 800;
    color: #3E313B;
}
.stat-label {
    font-size: 0.76rem;
    color: #7D6B78;
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

course_prefs = meta.get("course_prefs") or {}
if not isinstance(course_prefs, dict):
    course_prefs = {}

course_info = meta.get("course_info") or {}
if not isinstance(course_info, dict):
    course_info = {}

APP_META_KEYS = ["full_name", "daily_capacity", "exam_spread", "assign_spread", "course_prefs", "course_info"]

def save_profile_meta(updates: dict):
    current = {k: meta.get(k) for k in APP_META_KEYS if meta.get(k) is not None}
    current.update(updates)
    res = supabase.auth.update_user({"data": current})
    st.session_state["user"] = res.user

def flash(message: str, kind: str = "success"):
    st.session_state["flash"] = (kind, message)

def show_flash():
    item = st.session_state.pop("flash", None)
    if item:
        kind, message = item
        getattr(st, kind, st.info)(message)

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
        f'<circle cx="44" cy="44" r="{radius}" fill="none" stroke="#E6E3DD" stroke-width="7" />'
        f'<circle cx="44" cy="44" r="{radius}" fill="none" stroke="{stroke_color}" stroke-width="7" '
        f'stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{offset:.1f}" '
        f'stroke-linecap="round" transform="rotate(-90 44 44)" />'
        f'<text x="44" y="49" text-anchor="middle" fill="#15171C" font-size="16" font-weight="700">{pct}%</text>'
        f'</svg></div>'
    )

def render_mini_calendar(year: int, month: int, today_day: int, due_days: dict[int, str]) -> str:
    """due_days maps day-of-month -> busyness level (open/calm/steady/busy/peak)."""
    cal_matrix = pycal.monthcalendar(year, month)
    month_name = datetime(year, month, 1).strftime("%B %Y")
    parts = [
        f'<div style="text-align:center; font-weight:700; font-size:0.85rem; color:#15171C; margin-bottom:6px;">{month_name}</div>',
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
                lvl = due_days[d]
                parts.append(
                    f'<td><span class="cal-due" style="background:{bz.LEVEL_FILL[lvl]}; color:{bz.LEVEL_INK[lvl]};">{d}</span></td>'
                )
            else:
                parts.append(f"<td>{d}</td>")
        parts.append("</tr>")
    parts.append("</table>")
    return "".join(parts)

# ---------- Color Helpers ----------
EASY_RGB = (91, 179, 150)    # #5BB396
MID_RGB = (229, 169, 59)     # #E5A93B
HARD_RGB = (217, 107, 120)   # #D96B78

def difficulty_to_color(difficulty) -> str:
    try:
        t = (float(difficulty) - 1) / 4
    except (TypeError, ValueError):
        t = 0.5
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        start, end, frac = EASY_RGB, MID_RGB, t / 0.5
    else:
        start, end, frac = MID_RGB, HARD_RGB, (t - 0.5) / 0.5
    rgb = [round(start[i] + (end[i] - start[i]) * frac) for i in range(3)]
    return "#{:02X}{:02X}{:02X}".format(*rgb)

def safe_hex(value, fallback: str) -> str:
    if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        return value.upper()
    return fallback

def readable_text(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#15171C" if luminance > 0.62 else "#FFFFFF"

# ---------- Course Detection & Cleaning Helpers ----------
CODE_RE = re.compile(r"^([A-Za-z]{2,5})[\s_-]?(\d{4}[A-Za-z]?)$")

def normalize_course(raw) -> str:
    raw = str(raw or "").strip()
    if not raw:
        return "General"
    m = CODE_RE.match(raw)
    if m:
        return f"{m.group(1).upper()} {m.group(2).upper()}"
    return raw

IGNORED_PREFIXES = {
    "QUIZ", "EXAM", "TEST", "LABS", "PART", "WEEK", "UNIT", "PAGE", "XLSB", "FALL", "SPRG",
    "SPRING", "SUMMER", "WINTER", "TERM", "YEAR",
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "SEPT", "OCT", "NOV", "DEC",
}
COURSE_PATTERN = re.compile(r"(?<![A-Z])([A-Z]{2,5})[\s_-]?(\d{4}[A-Z]?)(?![0-9])")

def detect_course_code(text: str) -> str:
    if not text:
        return "General"
    upper = text.upper()

    stat_match = re.search(r"(?<![A-Z])STAT[\s_-]?(\d{4}[A-Z]?)(?![0-9])", upper)
    if stat_match:
        return f"STAT {stat_match.group(1)}"

    for dept, num in COURSE_PATTERN.findall(upper):
        if dept not in IGNORED_PREFIXES:
            return f"{dept} {num}"

    if re.search(r"\bSTATS?\b", upper):
        return "STAT 3122"

    return "General"

def clean_canvas_title(raw_summary: str) -> str:
    cleaned = re.sub(r"\s*\[20\d{4}-[^\]]*\]?", "", raw_summary).strip()
    return cleaned if cleaned else raw_summary.strip()

# ---------- Database & AI Helpers ----------
def call_gemini_with_fallback(contents, config=None):
    """Tries primary Gemini model with quick retries, then falls back to backup Flash models on 503/429."""
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    last_err = None
    for model_name in MODEL_FALLBACKS:
        for attempt in range(2):
            try:
                return client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                last_err = e
                err_str = str(e)
                if any(code in err_str for code in ["503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"]):
                    time.sleep(0.8 * (attempt + 1))
                    continue
                if "404" in err_str or "NOT_FOUND" in err_str:
                    break
                raise
    raise last_err

def load_user_df() -> pd.DataFrame:
    res = supabase.table("items").select("*").eq("user_id", user_id).execute()
    if not res.data:
        return pd.DataFrame(columns=["id", "course", "date", "title", "type", "hours", "difficulty", "done"])

    needs_reload = False
    for row in res.data:
        curr_course = (row.get("course") or "General").strip() or "General"
        curr_title = row.get("title") or ""
        new_course = detect_course_code(curr_title) if curr_course == "General" else curr_course
        new_course = normalize_course(new_course)
        new_title = clean_canvas_title(curr_title)

        if new_course != curr_course or new_title != curr_title:
            supabase.table("items").update({
                "course": new_course,
                "title": new_title,
            }).eq("id", row["id"]).execute()
            needs_reload = True

    if needs_reload:
        res = supabase.table("items").select("*").eq("user_id", user_id).execute()

    df = pd.DataFrame(res.data)
    df["course"] = df["course"].fillna("General").replace("", "General")
    df["date"] = pd.to_datetime(df["date"])
    df["hours"] = df["hours"].astype(float)
    df["difficulty"] = df["difficulty"].astype(int)
    return df

def add_rows_dedup(new_rows: list[dict]) -> tuple[int, int]:
    if not new_rows:
        return 0, 0
    existing = load_user_df()
    existing_map = {}
    if not existing.empty:
        for _, r in existing.iterrows():
            key = (r["date"].strftime("%Y-%m-%d"), str(r["title"]).strip().lower())
            existing_map[key] = (int(r["id"]), r["course"])

    unique_rows = []
    recategorized = 0
    for row in new_rows:
        clean_title = clean_canvas_title(str(row.get("title", "Untitled")).strip().replace(",", " "))
        date_str = str(row.get("date"))[:10]
        course = normalize_course(row.get("course"))
        if course == "General":
            course = detect_course_code(str(row.get("title", "")))
        key = (date_str, clean_title.lower())

        if key in existing_map:
            row_id, old_course = existing_map[key]
            if row_id is not None and old_course == "General" and course != "General":
                supabase.table("items").update({"course": course}).eq("id", row_id).execute()
                existing_map[key] = (row_id, course)
                recategorized += 1
            continue

        existing_map[key] = (None, course)
        unique_rows.append({
            "user_id": user_id,
            "course": course,
            "date": date_str,
            "title": clean_title,
            "type": row.get("type", "assignment"),
            "hours": float(row.get("hours", 1.5)),
            "difficulty": int(row.get("difficulty", 3)),
            "done": row.get("done", "no"),
        })

    if unique_rows:
        supabase.table("items").insert(unique_rows).execute()
    return len(unique_rows), recategorized

def clean_course_info(info) -> dict:
    entry = {}
    if not isinstance(info, dict):
        return entry
    try:
        total = int(info.get("expected_graded_items") or 0)
    except (TypeError, ValueError):
        total = 0
    if total > 0:
        entry["expected_total"] = total
    if info.get("end_date"):
        end = pd.to_datetime(info["end_date"], errors="coerce")
        if pd.notna(end):
            entry["end"] = end.strftime("%Y-%m-%d")
    return entry

def parse_ics_url(ics_url: str, days_back: int = 120) -> list[dict]:
    resp = requests.get(ics_url.strip(), timeout=15)
    resp.raise_for_status()
    cal = icalendar.Calendar.from_ical(resp.content)

    start_window = datetime.now() - timedelta(days=days_back)
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

        course = detect_course_code(raw_summary)
        if course == "General":
            course = detect_course_code(raw_desc)
        if course == "General":
            course = detect_course_code(raw_cats)

        clean_title = clean_canvas_title(raw_summary)
        lower = raw_summary.lower()
        uid = str(event.get("UID", "")).lower()
        if any(w in lower for w in ["exam", "midterm", "final", "test"]):
            item_type, diff = "exam", 5
        elif "quiz" in lower:
            item_type, diff = "quiz", 4
        elif "assignment" in uid or any(w in lower for w in ["homework", "hw", "project", "lab", "assignment", "paper"]):
            # Canvas gives every assignment a UID like "event-assignment-123", even when the
            # title has no keyword (e.g. "Hawkes Lesson 1.1"). Those are due items, not classes.
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
    res = call_gemini_with_fallback(
        contents=prompt,
        config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=0)),
    )
    raw = res.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)

def parse_syllabus_multimodal(uploaded_file=None, pasted_text: str = "", default_course: str = "") -> tuple[list[dict], dict]:
    contents = []
    prompt = f"""
    Read this syllabus and return ONLY one valid JSON object with two keys.

    "course_info": an object with these keys:
    - "course": course code/name (use "{default_course}" if provided, otherwise infer from the syllabus, or "General")
    - "expected_graded_items": the total number of graded assignments, quizzes, labs, projects, and exams in the whole course. Add up any counts the syllabus states (for example "10 homework assignments" plus "3 exams"). Use null if the syllabus does not give enough to know. Do not guess.
    - "end_date": "YYYY-MM-DD" for the last day of class or the final exam, or null if not stated (use 2026 if the year is omitted)

    "items": an array with every graded assignment, quiz, lab, project, and exam that has a due date. Each item has these exact keys:
    - "course": course code/name (use "{default_course}" if provided, otherwise infer from the syllabus, or "General")
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

    response = call_gemini_with_fallback(
        contents=contents,
        config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=0)),
    )
    raw = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(raw)
    if isinstance(data, list):
        return data, {}
    return data.get("items") or [], data.get("course_info") or {}

def build_local_fallback_plan(upcoming_items: pd.DataFrame, today: pd.Timestamp) -> str:
    if upcoming_items.empty:
        return "You have no unfinished tasks due in the next 14 days—enjoy the breathing room!"
    lines = ["*Gemini servers are experiencing high demand, so here is an auto-balanced plan built directly from your deadlines:*\n"]
    sorted_tasks = upcoming_items.sort_values(["date", "difficulty"], ascending=[True, False])
    for i in range(7):
        day = today + pd.Timedelta(days=i)
        day_tasks = sorted_tasks[sorted_tasks["date"].dt.normalize() >= day].head(2)
        if not day_tasks.empty:
            bullets = ", ".join(
                f"**{r['course']}** ({r['title']} — {min(r['hours'], round(daily_capacity / 2, 1))}h)"
                for _, r in day_tasks.iterrows()
            )
            lines.append(f"- **{day.strftime('%a %b %d')}:** Focus on {bullets}")
    return "\n".join(lines)

def stream_study_plan(df: pd.DataFrame, load_df: pd.DataFrame):
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    today = pd.Timestamp.now().normalize()
    upcoming_items = df[(df["done"] == "no") & (df["date"] >= today) & (df["date"] <= today + pd.Timedelta(days=14))]
    peak_days = load_df[(load_df["date"] >= today) & (load_df["date"] <= today + pd.Timedelta(days=14)) & (load_df["level"].isin(["busy", "peak"]))]

    items_summary = upcoming_items[["course", "date", "title", "type", "hours", "difficulty"]].to_dict(orient="records")
    peaks_summary = peak_days[["date", "level"]].to_dict(orient="records")

    prompt = f"""
    You are an academic coach for {display_name}. Today is {today.strftime('%Y-%m-%d')}.
    Daily capacity: {daily_capacity}h/day.
    Busy and peak days: {peaks_summary}
    Tasks (next 14 days): {items_summary}

    Write a concise, bulleted 7-day study plan to flatten peak crunch days. Name exact courses, tasks, and realistic hour blocks within {daily_capacity}h/day. Keep it brief and scannable.
    """
    cfg = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        max_output_tokens=700,
    )

    for model_name in MODEL_FALLBACKS:
        try:
            response = client.models.generate_content_stream(
                model=model_name,
                contents=prompt,
                config=cfg,
            )
            yielded_any = False
            for chunk in response:
                if chunk.text:
                    yielded_any = True
                    yield chunk.text
            if yielded_any:
                return
        except Exception as e:
            err_str = str(e)
            if any(code in err_str for code in ["503", "429", "404", "UNAVAILABLE", "NOT_FOUND", "RESOURCE_EXHAUSTED"]):
                time.sleep(0.6)
                continue
            raise

    yield build_local_fallback_plan(upcoming_items, today)

# ---------- Left Taupe Sidebar Navigation & Importers ----------
with st.sidebar:
    render_html(
        f'<div style="font-size:1.35rem; font-weight:800; color:#15171C; letter-spacing:-0.5px; margin-bottom:4px; font-family:var(--font-display);">'
        f'Plan<span style="color:#686D7A;">tech</span></div>'
        f'<div class="profile-box"><div class="avatar-circle">{esc(initials)}</div>'
        f'<div><div style="font-weight:700; color:#15171C; font-size:0.95rem;">{esc(display_name)}</div>'
        f'<div style="font-size:0.75rem; color:#686D7A;">{esc(user.email)}</div></div></div>'
    )

    nav_page = st.radio(
        "Navigation",
        ["Dashboard", "Workload Forecast", "Full Calendar", "Master Task Editor", "Courses", "Course Progress", "AI Study Coach"],
        label_visibility="collapsed",
    )

    st.divider()

    with st.expander("Import Calendar (.ics)"):
        ics_link = st.text_input("Paste secret .ics URL", placeholder="https://...")
        days_back = st.number_input(
            "Include events from the last (days)", min_value=7, max_value=365, value=120, step=1,
            help="Go back far enough to reach your first assignment, so course progress counts work you already finished.",
        )
        if st.button("Sync Calendar") and ics_link:
            try:
                imported = parse_ics_url(ics_link, int(days_back))
                added_count, sorted_count = add_rows_dedup(imported)
                flash(f"Added {added_count} new events and sorted {sorted_count} existing events into their courses.")
                st.rerun()
            except Exception as e:
                st.error(f"Sync failed: {e}")

    with st.expander("AI Syllabus Extractor"):
        course_tag = st.text_input("Course Tag (optional)", placeholder="e.g., MATH 2171")
        syl_file = st.file_uploader("PDF, Word (.docx), or Image", type=["pdf", "docx", "png", "jpg", "jpeg"])
        syl_text = st.text_area("Or paste syllabus text", height=80)
        if st.button("Extract Deadlines") and (syl_file is not None or syl_text.strip()):
            try:
                extracted, info = parse_syllabus_multimodal(syl_file, syl_text, course_tag)
                added_count, _ = add_rows_dedup(extracted)
                message = f"Added {added_count} new items!"
                info_course = normalize_course(course_tag) if course_tag.strip() else normalize_course(info.get("course"))
                entry = clean_course_info(info)
                if entry and info_course != "General":
                    merged_info = {**course_info, info_course: {**(course_info.get(info_course) or {}), **entry}}
                    save_profile_meta({"course_info": merged_info})
                    found = []
                    if "expected_total" in entry:
                        found.append(f"{entry['expected_total']} graded items")
                    if "end" in entry:
                        found.append(f"ends {entry['end']}")
                    message += f" Saved the {info_course} timeline from the syllabus ({', '.join(found)})."
                flash(message)
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
        if st.button("Save Settings"):
            try:
                save_profile_meta({
                    "full_name": updated_name.strip() or display_name,
                    "daily_capacity": new_cap,
                })
                st.rerun()
            except Exception as e:
                st.error(f"Could not save settings: {e}")

    st.divider()
    if st.button("Log Out", use_container_width=True):
        supabase.auth.sign_out()
        st.session_state["user"] = None
        st.session_state["session"] = None
        st.rerun()

show_flash()

# ---------- Load Data & Top Header Row ----------
df = load_user_df()
now_ny = datetime.now(ZoneInfo("America/New_York"))
today_local = pd.Timestamp(now_ny.date())

top_left, top_right = st.columns([2.2, 1.5])
with top_left:
    render_html(f"<h1 style='margin-bottom:0; color:#15171C; font-weight:800;'>{esc(get_greeting(display_name))}</h1>")
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

# ---------- Course Colors ----------
all_courses = sorted(df["course"].unique().tolist())
course_avg = df.groupby("course")["difficulty"].mean().to_dict()

def course_color(course: str) -> str:
    pref = course_prefs.get(course) or {}
    auto = difficulty_to_color(pref.get("difficulty", course_avg.get(course, 3)))
    if pref.get("custom"):
        return safe_hex(pref.get("color"), auto)
    return auto

def course_badge(course: str) -> str:
    color = course_color(course)
    return f'<span class="pill-badge" style="background-color:{color}; color:{readable_text(color)};">{esc(course)}</span>'

# ---------- Course Progress (graded work only) ----------
UNGRADED_TYPES = {"recurring", "job"}

def course_progress(course_df: pd.DataFrame, info: dict):
    graded = course_df[~course_df["type"].isin(UNGRADED_TYPES)]
    if graded.empty:
        return None

    dates = graded["date"].dt.normalize()
    is_done = graded["done"] == "yes"
    on_calendar = len(graded)

    try:
        expected = int(info.get("expected_total") or 0)
    except (TypeError, ValueError):
        expected = 0
    total = max(on_calendar, expected)
    not_posted = max(expected - on_calendar, 0)

    done = int(is_done.sum())
    past_due_mask = (dates < today_local) & ~is_done
    ahead_on_calendar = int(((dates >= today_local) & ~is_done).sum())

    start = dates.min()
    end = dates.max()
    end_source = "last item on your calendar"
    if info.get("end"):
        parsed_end = pd.to_datetime(info["end"], errors="coerce")
        if pd.notna(parsed_end) and parsed_end.normalize() >= end:
            end = parsed_end.normalize()
            end_source = "course end date"
    span_days = (end - start).days
    elapsed = None if span_days <= 0 else round(min(max((today_local - start).days / span_days, 0), 1) * 100)

    total_hours = float(graded["hours"].sum())
    done_hours = float(graded.loc[is_done, "hours"].sum())

    return {
        "pct": round(done / total * 100),
        "done": done,
        "total": total,
        "ahead": ahead_on_calendar + not_posted,
        "past_due": int(past_due_mask.sum()),
        "not_posted": not_posted,
        "start": start,
        "end": end,
        "end_source": end_source,
        "elapsed": elapsed,
        "hours_pct": round(done_hours / total_hours * 100) if total_hours else 0,
        "past_due_ids": graded.loc[past_due_mask, "id"].astype(int).tolist(),
        "past_due_df": graded.loc[past_due_mask, ["date", "title", "type", "hours"]].sort_values("date"),
    }

progress = {}
for _course in all_courses:
    _p = course_progress(df[df["course"] == _course], course_info.get(_course) or {})
    if _p:
        progress[_course] = _p

# Course Filter Pills
selected_courses = st.multiselect("Active Courses", options=all_courses, default=all_courses, label_visibility="collapsed")
filtered_df = df[df["course"].isin(selected_courses)].copy()

if filtered_df.empty:
    st.warning("Select at least one course above.")
    st.stop()

chips_html = "".join(
    f'<span class="course-chip" style="background-color:{course_color(c)}; color:{readable_text(course_color(c))};">{esc(c)}</span>'
    for c in selected_courses
)
render_html(f'<div class="chip-row">{chips_html}</div>')

# ---------- Compute Busyness & Completion Metrics ----------
# Busyness = what's DUE each day (see busyness.py). No spreading, no hours or difficulty.
range_start = min(filtered_df["date"].min(), today_local)
range_end = max(filtered_df["date"].max(), today_local)
daily_df = bz.daily_scores(filtered_df[["date", "course", "type"]], range_start, range_end)
weekly_df = bz.weekly_scores(daily_df)
course_daily_df = bz.course_daily_scores(filtered_df[["date", "course", "type"]])
level_by_day = dict(zip(daily_df["date"], daily_df["level"]))

total_items = len(filtered_df)
done_items = int((filtered_df["done"] == "yes").sum())
overall_pct = round((done_items / total_items) * 100) if total_items else 0

course_stats = []
for c_name in selected_courses:
    c_sub = filtered_df[filtered_df["course"] == c_name]
    c_pct = round(((c_sub["done"] == "yes").sum() / len(c_sub)) * 100) if len(c_sub) else 0
    course_stats.append((c_name, c_pct))


def short_label(row) -> str:
    title = str(row["title"])
    title = title if len(title) <= 22 else title[:21] + "…"
    return f"{row['course']} {title}"


def top_items(start, end, n=3) -> list[str]:
    """The heaviest items due between start and end (inclusive), for labels and hovers."""
    sub = filtered_df[(filtered_df["date"] >= start) & (filtered_df["date"] <= end)].copy()
    if sub.empty:
        return []
    sub["w"] = sub["type"].map(lambda t: bz.TYPE_WEIGHTS.get(t, bz.DEFAULT_WEIGHT))
    sub = sub[sub["w"] > 0].sort_values(["w", "date"], ascending=[False, True])
    return [short_label(r) for _, r in sub.head(n).iterrows()]


def fmt_range(a, b) -> str:
    return f"{a.strftime('%b %-d')}–{b.strftime('%-d')}" if a.month == b.month else f"{a.strftime('%b %-d')}–{b.strftime('%b %-d')}"


def semester_figure(view: str, height: int = 340) -> go.Figure:
    """The hero graph: one line for the whole semester, dots colored by busyness level."""
    if view == "Weeks":
        data = weekly_df.rename(columns={"week_start": "x"}).copy()
        data["label"] = [fmt_range(a, b) for a, b in zip(data["x"], data["week_end"])]
        data["is_past"] = data["week_end"] < today_local
        data["hover"] = [
            f"<b>Week of {lbl}</b> · {lvl.capitalize()}<br>{cnt} due<br>" + "<br>".join(top_items(a, b))
            for lbl, lvl, cnt, a, b in zip(data["label"], data["level"], data["count"], data["x"], data["week_end"])
        ]
        dot_size = 13
    else:
        data = daily_df.rename(columns={"date": "x"}).copy()
        data["is_past"] = data["x"] < today_local
        data["hover"] = [
            f"<b>{x.strftime('%a %b %-d')}</b> · {lvl.capitalize()}<br>{cnt} due<br>" + "<br>".join(top_items(x, x))
            for x, lvl, cnt in zip(data["x"], data["level"], data["count"])
        ]
        dot_size = 7

    fig = go.Figure()
    # Soft area + line. Past is faded, future is full strength.
    for past, opacity in [(True, 0.45), (False, 1.0)]:
        seg = data[data["is_past"] == past]
        if past and not data[~data["is_past"]].empty:
            seg = pd.concat([seg, data[~data["is_past"]].head(1)])  # connect the two segments
        if seg.empty:
            continue
        fig.add_trace(go.Scatter(
            x=seg["x"], y=seg["score"], mode="lines",
            line=dict(color="#15171C", width=2.5, shape="spline", smoothing=0.5),
            fill="tozeroy", fillcolor="rgba(21,23,28,0.04)",
            opacity=opacity, hoverinfo="skip", showlegend=False,
        ))
    dots = data[data["level"] != "open"]
    fig.add_trace(go.Scatter(
        x=dots["x"], y=dots["score"], mode="markers",
        marker=dict(
            size=dot_size,
            color=[bz.LEVEL_FILL[l] for l in dots["level"]],
            line=dict(width=1.5, color=[bz.LEVEL_INK[l] for l in dots["level"]]),
            opacity=[0.45 if p else 1.0 for p in dots["is_past"]],
        ),
        hovertext=dots["hover"], hoverinfo="text", showlegend=False,
    ))
    # Peaks get labeled by their cause, so the hardest stretches explain themselves.
    if view == "Weeks":
        for _, r in data[data["level"] == "peak"].iterrows():
            cause = top_items(r["x"], r["week_end"], 1)
            if cause:
                fig.add_annotation(
                    x=r["x"], y=r["score"], text=cause[0], showarrow=False, yshift=18,
                    font=dict(size=11, color=bz.LEVEL_INK["peak"], family=CHART_FONT),
                    bgcolor="#fff0ec", borderpad=3,
                )
    # Today
    fig.add_vline(x=today_local, line_dash="dash", line_color="#15171C", line_width=1.2)
    fig.add_annotation(
        x=today_local, y=1.02, yref="paper", text="TODAY", showarrow=False,
        font=dict(size=10, color="#FFFFFF", family=CHART_FONT), bgcolor="#15171C", borderpad=3,
    )
    ymax = max(data["score"].max(), 1) * 1.28
    fig.update_layout(
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        height=height, margin=dict(l=4, r=4, t=24, b=8),
        xaxis=dict(showgrid=False, showline=False, tickformat="%b", dtick="M1", ticklabelmode="period",
                   tickfont=dict(color="#686D7A", size=12)),
        yaxis=dict(visible=False, range=[0, ymax]),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#E6E3DD", font=dict(color="#15171C", family=CHART_FONT)),
        font=dict(family=CHART_FONT),
    )
    return fig


# ---------- Page Views ----------
if nav_page == "Dashboard":
    # 1. The hero: the whole semester as one line
    hardest = weekly_df.loc[weekly_df["score"].idxmax()]
    ahead = weekly_df[(weekly_df["week_start"] > today_local) & (weekly_df["level"].isin(["busy", "peak"]))]
    sub_parts = [f"Hardest week: <b>{fmt_range(hardest['week_start'], hardest['week_end'])}</b>"]
    if not ahead.empty:
        nxt = ahead.iloc[0]
        sub_parts.append(f"Next heavy week: <b>{fmt_range(nxt['week_start'], nxt['week_end'])}</b> ({nxt['level']})")
    legend = "".join(
        f'<span><i style="background:{bz.LEVEL_FILL[l]}; border:1px solid {bz.LEVEL_INK[l]};"></i>{l.capitalize()}</span>'
        for l in bz.LEVELS
    )
    with st.container(key="hero"):
        h_left, h_right = st.columns([4, 1.1])
        with h_left:
            render_html(
                f'<div class="hero-title">Your semester</div>'
                f'<div class="hero-sub">{" · ".join(sub_parts)}</div>'
            )
        with h_right:
            view = st.segmented_control("Zoom", ["Weeks", "Days"], default="Weeks", label_visibility="collapsed", key="hero_zoom") or "Weeks"
        st.plotly_chart(semester_figure(view), use_container_width=True, config={"displayModeBar": False})
        render_html(f'<div class="legend" style="padding:0 0 10px 2px;">{legend}</div>')

    # 2. The detail, one level down
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
                    f'<div class="pill-row"><div class="pill-left">{course_badge(r["course"])}<span class="pill-title">{esc(r["title"])}</span></div><span class="pill-sub">Diff {int(r["difficulty"])}/5</span></div>'
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
                    f'<div class="pill-row"><div class="pill-left"><span class="course-dot" style="background-color:{course_color(r["course"])};"></span><span class="pill-badge">{r["date"].strftime("%b %d")}</span><span class="pill-title">{esc(r["title"])}</span></div><span class="pill-sub">{r["hours"]}h</span></div>'
                    for _, r in upcoming.iterrows()
                )
            render_html(f'<div class="bento-card"><div class="bento-title">Upcoming Events</div>{up_html}</div>')

        month_due = filtered_df[
            (filtered_df["date"].dt.year == now_ny.year) & (filtered_df["date"].dt.month == now_ny.month)
        ]
        due_day_levels = {
            d.day: level_by_day.get(d.normalize(), "calm")
            for d in month_due["date"]
            if level_by_day.get(d.normalize(), "open") != "open"
        }
        cal_html = render_mini_calendar(now_ny.year, now_ny.month, now_ny.day, due_day_levels)

        next_three = filtered_df[filtered_df["date"] >= today_local].sort_values("date").head(3)
        if next_three.empty:
            sched_pills = '<div class="pill-row"><span class="pill-sub">No events left this week.</span></div>'
        else:
            sched_pills = "".join(
                f'<div class="pill-row"><div class="pill-left"><div class="date-circle" style="border:3px solid {course_color(r["course"])};">{r["date"].day}</div><div><div class="pill-title">{esc(r["title"])}</div><div class="pill-sub">{esc(r["course"])} • {esc(r["type"]).capitalize()}</div></div></div><span class="pill-sub">{r["hours"]}h</span></div>'
                for _, r in next_three.iterrows()
            )

        render_html(
            f'<div class="bento-card"><div class="bento-title">My Schedule</div>'
            f'<div style="display:grid; grid-template-columns: 1.05fr 1.35fr; gap:16px; align-items:center;">'
            f'<div>{cal_html}</div><div>{sched_pills}</div></div></div>'
        )


    with right_rail:
        rings_html = render_progress_ring("Overall Coursework", overall_pct, "#15171C")
        for c_name, c_pct in course_stats:
            rings_html += render_progress_ring(c_name, c_pct, course_color(c_name))

        render_html(
            f'<div class="plum-panel">{rings_html}'
            f'<div style="text-align:center; font-size:0.82rem; font-weight:600; color:#464B57; padding-top:4px;">'
            f'{done_items} of {total_items} graded items done</div></div>'
        )

elif nav_page == "Workload Forecast":
    st.subheader("Semester Busyness")
    chart_mode = st.radio("View Mode", ["Weeks", "Days", "Stacked by Course"], horizontal=True)
    with st.expander("How busyness is scored"):
        st.markdown(
            "Each item counts on its **due date**: exam 4, quiz 3, assignment 2, reading or job 1. "
            "Class meetings count 0. Many items from one class on one day count as one heavy day.\n\n"
            "- **Daily:** open 0 · calm under 4 · steady 4–6.5 · busy 7–9.5 · peak 10+\n"
            "- **Weekly:** calm under 10 · steady 10–14.5 · busy 15–20.5 · peak 21+"
        )

    if chart_mode in ("Weeks", "Days"):
        st.plotly_chart(semester_figure(chart_mode, height=440), use_container_width=True, config={"displayModeBar": False})
    else:
        fig_stack = px.area(
            course_daily_df, x="date", y="score", color="course",
            color_discrete_map={c: course_color(c) for c in course_daily_df["course"].unique()},
        )
        fig_stack.update_layout(paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", height=440,
                                yaxis=dict(title="Busyness score"), font=dict(family=CHART_FONT))
        st.plotly_chart(fig_stack, use_container_width=True)

elif nav_page == "Full Calendar":
    st.subheader("Interactive Semester Calendar")
    color_mode = st.radio("Color events by", ["Course", "Difficulty"], horizontal=True)
    cal_events = []
    for _, r in filtered_df.iterrows():
        if r["done"] == "yes":
            bg = "#9ca3af"
        elif color_mode == "Course":
            bg = course_color(r["course"])
        else:
            bg = "#D96B78" if r["difficulty"] >= 4 else ("#E5A93B" if r["difficulty"] == 3 else "#5BB396")
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
        key=f"full_cal_grid_{color_mode}",
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
                    "course": normalize_course(row["course"]),
                    "date": str(row["date"]),
                    "title": str(row["title"]).strip(),
                    "type": row["type"],
                    "hours": float(row["hours"]),
                    "difficulty": int(row["difficulty"]),
                }).eq("id", rid).execute()
        st.success("Saved!")
        st.rerun()

elif nav_page == "Courses":
    st.subheader("Course Colors & Difficulty")
    st.caption("Rate how hard each course is and it gets a color from green (easy) to red (hard). Want your own color? Tick \"Use my own color\" and pick one.")
    render_html(
        '<div style="height:12px; border-radius:999px; background:linear-gradient(90deg, #5BB396, #E5A93B, #D96B78); margin:8px 0 4px 0;"></div>'
        '<div style="display:flex; justify-content:space-between; font-size:0.75rem; color:#7D6B78; margin-bottom:14px;">'
        '<span>1 · Easy</span><span>3 · Moderate</span><span>5 · Hard</span></div>'
    )

    with st.form("course_prefs_form"):
        h1, h2, h3, h4 = st.columns([2, 3, 1.7, 1.2])
        h1.caption("Course")
        h2.caption("Difficulty (1 easy, 5 hard)")
        h3.caption("Use my own color")
        h4.caption("Color")

        new_prefs = {}
        for c in all_courses:
            pref = course_prefs.get(c) or {}
            default_diff = max(1, min(5, int(pref.get("difficulty", round(course_avg.get(c, 3))))))
            auto_color = difficulty_to_color(default_diff)

            c1, c2, c3, c4 = st.columns([2, 3, 1.7, 1.2])
            with c1:
                render_html(
                    f'<span class="course-chip" style="background-color:{course_color(c)}; color:{readable_text(course_color(c))};">{esc(c)}</span>'
                )
            diff_val = c2.slider(
                f"Difficulty for {c}", 1, 5, default_diff, key=f"pref_diff_{c}", label_visibility="collapsed",
            )
            use_custom = c3.checkbox(
                f"Use my own color for {c}", value=bool(pref.get("custom", False)), key=f"pref_custom_{c}",
                label_visibility="collapsed",
            )
            picked = c4.color_picker(
                f"Color for {c}", value=safe_hex(pref.get("color"), auto_color), key=f"pref_color_{c}",
                label_visibility="collapsed",
            )
            new_prefs[c] = {"difficulty": int(diff_val), "custom": bool(use_custom), "color": picked}

        saved = st.form_submit_button("Save course colors", type="primary")

    if saved:
        try:
            save_profile_meta({"course_prefs": {**course_prefs, **new_prefs}})
            flash("Course colors saved.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not save course colors: {e}")

    if course_prefs and st.button("Reset all to automatic colors"):
        try:
            save_profile_meta({"course_prefs": {}})
            flash("Course colors reset to the green to red scale.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not reset course colors: {e}")

    st.divider()
    st.markdown("#### Rename or merge a course")
    st.caption("Wrong label? Rename a course, or type the name of another course to merge the two. To move a single task, change its course in the Master Task Editor.")
    counts = (
        df.groupby("course").size().reset_index(name="Tasks").rename(columns={"course": "Course"})
    )
    st.dataframe(counts, hide_index=True, use_container_width=True)

    rn1, rn2 = st.columns(2)
    old_name = rn1.selectbox("Course to rename", all_courses, key="rename_old")
    new_name_raw = rn2.text_input("New name", placeholder="e.g., MATH 2171", key="rename_new")
    if st.button("Rename course"):
        target = normalize_course(new_name_raw)
        if not new_name_raw.strip():
            st.warning("Type the new course name first.")
        elif target == old_name:
            st.info("That is already the course name.")
        else:
            try:
                supabase.table("items").update({"course": target}).eq("user_id", user_id).eq("course", old_name).execute()
                if old_name in course_prefs:
                    moved = dict(course_prefs)
                    moved.setdefault(target, moved[old_name])
                    moved.pop(old_name, None)
                    save_profile_meta({"course_prefs": moved})
                flash(f"Renamed {old_name} to {target}.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not rename the course: {e}")

elif nav_page == "Course Progress":
    st.subheader("Course Progress")
    st.caption("Progress counts graded work on your calendar: assignments, quizzes, exams, and readings. Class meetings and work shifts are left out.")

    shown = {c: p for c, p in progress.items() if c in selected_courses}
    if not shown:
        st.info("No graded work yet. Sync your Canvas calendar or add assignments, quizzes, and exams to see course progress.")
    else:
        if "General" in shown:
            st.info("Items filed under General are not a real course. Sort them into courses on the Courses page.")

        all_done = sum(p["done"] for p in shown.values())
        all_total = sum(p["total"] for p in shown.values())
        all_pct = round(all_done / all_total * 100) if all_total else 0
        st.markdown(f"**All selected courses: {all_pct}%** ({all_done} of {all_total} graded items done)")

        for c, p in shown.items():
            color = course_color(c)
            done_w = p["done"] / p["total"] * 100
            late_w = p["past_due"] / p["total"] * 100
            elapsed_txt = f'{p["elapsed"]}%' if p["elapsed"] is not None else "n/a"
            span_note = f'First item {p["start"].strftime("%b %d")} to {p["end"].strftime("%b %d")} ({p["end_source"]})'
            if p["not_posted"] > 0:
                span_note += f' · {p["not_posted"]} not on your calendar yet (from the syllabus total)'

            render_html(
                f'<div class="bento-card">'
                f'<div style="display:flex; justify-content:space-between; align-items:center;">'
                f'<span class="course-chip" style="background-color:{color}; color:{readable_text(color)};">{esc(c)}</span>'
                f'<span style="font-size:1.6rem; font-weight:800; color:#3E313B;">{p["pct"]}%</span></div>'
                f'<div class="progress-track">'
                f'<div class="progress-seg" style="width:{done_w:.1f}%; background-color:{color};"></div>'
                f'<div class="progress-seg" style="width:{late_w:.1f}%; background-color:#C9A7AE;"></div></div>'
                f'<div class="stat-grid">'
                f'<div class="stat-box"><div class="stat-num">{p["done"]} of {p["total"]}</div><div class="stat-label">graded items done</div></div>'
                f'<div class="stat-box"><div class="stat-num">{p["ahead"]}</div><div class="stat-label">still ahead</div></div>'
                f'<div class="stat-box"><div class="stat-num">{p["past_due"]}</div><div class="stat-label">past due, not checked off</div></div>'
                f'<div class="stat-box"><div class="stat-num">{elapsed_txt}</div><div class="stat-label">of the course timeline passed</div></div>'
                f'<div class="stat-box"><div class="stat-num">{p["hours_pct"]}%</div><div class="stat-label">of estimated work hours done</div></div>'
                f'</div>'
                f'<div class="pill-sub" style="margin-top:10px;">{esc(span_note)}</div></div>'
            )

            if p["past_due"]:
                with st.expander(f'{p["past_due"]} past-due items in {c} are not checked off'):
                    past_df = p["past_due_df"].copy()
                    past_df["date"] = past_df["date"].dt.strftime("%b %d")
                    st.dataframe(past_df, hide_index=True, use_container_width=True)
                    st.caption("Finished these already? Mark them done and your progress updates.")
                    if st.button(f"Mark these {p['past_due']} as done", key=f"markdone_{c}"):
                        try:
                            supabase.table("items").update({"done": "yes"}).in_("id", p["past_due_ids"]).execute()
                            flash(f"Marked {p['past_due']} items in {c} as done.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Could not update those items: {e}")

        st.divider()
        st.markdown("#### Course totals from the syllabus")
        st.caption(
            "Your calendar only lists work that has been posted so far. Enter how many graded items the whole course has "
            "and the last day of class, and progress will count what is still to come. "
            "The AI Syllabus Extractor fills these in when your syllabus states them."
        )
        with st.form("course_totals_form"):
            f1, f2, f3 = st.columns([2, 3, 2])
            f1.caption("Course")
            f2.caption("Graded items in the whole course (0 = unknown)")
            f3.caption("Last day of class")

            totals_input = {}
            for c in progress:
                info = course_info.get(c) or {}
                existing_end = None
                if info.get("end"):
                    parsed_end = pd.to_datetime(info["end"], errors="coerce")
                    if pd.notna(parsed_end):
                        existing_end = parsed_end.date()

                g1, g2, g3 = st.columns([2, 3, 2])
                with g1:
                    render_html(
                        f'<span class="course-chip" style="background-color:{course_color(c)}; color:{readable_text(course_color(c))};">{esc(c)}</span>'
                    )
                total_val = g2.number_input(
                    f"Graded items in {c}", min_value=0, max_value=500, value=int(info.get("expected_total") or 0),
                    step=1, key=f"tot_{c}", label_visibility="collapsed",
                )
                end_val = g3.date_input(
                    f"Last day of class for {c}", value=existing_end, key=f"end_{c}", label_visibility="collapsed",
                )
                totals_input[c] = (int(total_val), end_val)

            totals_saved = st.form_submit_button("Save course totals", type="primary")

        if totals_saved:
            try:
                new_info = dict(course_info)
                for c, (total_val, end_val) in totals_input.items():
                    entry = {}
                    if total_val > 0:
                        entry["expected_total"] = total_val
                    if end_val:
                        entry["end"] = end_val.strftime("%Y-%m-%d")
                    if entry:
                        new_info[c] = entry
                    else:
                        new_info.pop(c, None)
                save_profile_meta({"course_info": new_info})
                flash("Course totals saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not save course totals: {e}")

elif nav_page == "AI Study Coach":
    st.subheader("AI Crunch-Week Study Plan Generator")
    st.write(f"Generates a streaming 7-day plan calibrated to your **{daily_capacity}h/day** study capacity.")
    if st.button("Generate My 7-Day Study Plan", type="primary"):
        try:
            plan_text = st.write_stream(stream_study_plan(filtered_df, daily_df))
            st.session_state["cached_study_plan"] = plan_text
        except Exception as e:
            st.error(f"Could not generate study plan: {e}")
    elif "cached_study_plan" in st.session_state:
        st.markdown(st.session_state["cached_study_plan"])