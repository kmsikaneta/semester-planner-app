import html as html_lib
import json
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
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
import weather as wx

APP_NAME = "Plantech"  # working name; change here and in assets/wordmark.svg
TZ = ZoneInfo("America/New_York")
CHART_FONT = "Plus Jakarta Sans, -apple-system, Segoe UI, Helvetica, Arial, sans-serif"
ROOT = Path(__file__).parent

st.set_page_config(page_title=APP_NAME, page_icon=":material/partly_cloudy_day:", layout="wide", initial_sidebar_state="collapsed")

MODEL_FALLBACKS = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.0-flash"]

# Initialize Supabase client
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# In-memory background job registry (survives page switches & browser disconnects)
@st.cache_resource
def get_study_plan_jobs() -> dict:
    return {}

STUDY_PLAN_JOBS = get_study_plan_jobs()

def esc(text) -> str:
    return html_lib.escape(str(text)).replace("\n", " ").replace("\r", " ")

def render_html(raw_html: str):
    single_line = " ".join(line.strip() for line in raw_html.splitlines() if line.strip())
    st.markdown(single_line, unsafe_allow_html=True)

# ---------- Design system styles (styles.css, matches tokens.css) ----------
@st.cache_data
def _styles() -> str:
    return (ROOT / "styles.css").read_text()

st.html(f"<style>{_styles()}</style>")

LOGO = ROOT / "assets" / "wordmark.svg"
if LOGO.exists():
    st.logo(str(LOGO), size="large")

TYPE_LABELS = {
    "exam": "Exam", "quiz": "Quiz", "assignment": "Assignment", "reading": "Reading",
    "recurring": "Class meeting", "job": "Work or event",
}
TYPE_OPTIONS = list(TYPE_LABELS.keys())

def type_label(t) -> str:
    return TYPE_LABELS.get(str(t), str(t).capitalize())

# ---------- Sign in & password recovery ----------
if "user" not in st.session_state:
    st.session_state["user"] = None
if "session" not in st.session_state:
    st.session_state["session"] = None
if "password_recovery_mode" not in st.session_state:
    st.session_state["password_recovery_mode"] = False

q_params = st.query_params
if "code" in q_params and st.session_state["user"] is None:
    try:
        res = supabase.auth.exchange_code_for_session({"auth_code": q_params["code"]})
        if res.user:
            st.session_state["user"] = res.user
            st.session_state["session"] = res.session
            st.session_state["password_recovery_mode"] = True
            st.query_params.clear()
            st.rerun()
    except Exception:
        pass
elif q_params.get("type") == "recovery" and "token_hash" in q_params and st.session_state["user"] is None:
    try:
        res = supabase.auth.verify_otp({"token_hash": q_params["token_hash"], "type": "recovery"})
        if res.user:
            st.session_state["user"] = res.user
            st.session_state["session"] = res.session
            st.session_state["password_recovery_mode"] = True
            st.query_params.clear()
            st.rerun()
    except Exception:
        pass

if st.session_state["session"] is not None:
    supabase.auth.set_session(
        st.session_state["session"].access_token,
        st.session_state["session"].refresh_token,
    )

def auth_intro():
    render_html(
        '<div style="height:36px;"></div>'
        f'<div class="auth-title">See your whole semester in one line.</div>'
        f'<div class="auth-sub">Connect Canvas, add your syllabi, and spot the hard weeks before they hit.</div>'
        + "".join(
            f'<div class="auth-line"><span class="level-chip" data-level="{lvl}">{wx.icon(lvl, 15)}{wx.name(lvl)}</span>'
            f'<span class="muted" style="font-size:0.85rem; margin-left:8px;">{esc(txt)}</span></div>'
            for lvl, txt in [("calm", "Light days"), ("busy", "Full days"), ("peak", "Your heaviest days")]
        )
    )

if st.session_state["user"] is not None and st.session_state.get("password_recovery_mode"):
    left, _, right = st.columns([1.1, 0.15, 1])
    with left:
        auth_intro()
    with right:
        render_html('<div class="section-title">Choose a new password</div>')
        with st.form("reset_new_pw_form"):
            new_pw = st.text_input("New password (6+ characters)", type="password")
            confirm_pw = st.text_input("Type it again", type="password")
            if st.form_submit_button("Save new password", type="primary", use_container_width=True):
                if len(new_pw) < 6:
                    st.error("Use at least 6 characters.")
                elif new_pw != confirm_pw:
                    st.error("Those passwords don't match.")
                else:
                    try:
                        res = supabase.auth.update_user({"password": new_pw})
                        st.session_state["user"] = res.user
                        st.session_state["password_recovery_mode"] = False
                        st.success("Password saved. Opening your semester...")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Couldn't save that password: {e}")
    st.stop()

if st.session_state["user"] is None:
    left, _, right = st.columns([1.1, 0.15, 1])
    with left:
        auth_intro()
    with right:
        tab_login, tab_signup, tab_forgot = st.tabs(["Log in", "Create account", "Forgot password"])

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Log in", type="primary", use_container_width=True):
                    try:
                        res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                        st.session_state["user"] = res.user
                        st.session_state["session"] = res.session
                        st.rerun()
                    except Exception as e:
                        st.error(f"Couldn't log in: {e}")

        with tab_signup:
            with st.form("signup_form"):
                full_name = st.text_input("First name")
                new_email = st.text_input("Email")
                new_password = st.text_input("Password (6+ characters)", type="password")
                if st.form_submit_button("Create account", type="primary", use_container_width=True):
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
                        st.error(f"Couldn't create your account: {e}")

        with tab_forgot:
            with st.form("forgot_password_form"):
                reset_email = st.text_input("Email on your account")
                if st.form_submit_button("Send reset link", use_container_width=True):
                    if not reset_email.strip():
                        st.warning("Add your email first.")
                    else:
                        try:
                            supabase.auth.reset_password_for_email(
                                reset_email.strip(),
                                options={"redirect_to": "https://semester-planner.streamlit.app"},
                            )
                            st.success("Sent. Check your inbox (and spam) for the link.")
                        except Exception as e:
                            st.error(f"Couldn't send the email: {e}")

    st.stop()

# ---------- User profile & preferences ----------
user = st.session_state["user"]
user_id = user.id
meta = user.user_metadata or {}
display_name = meta.get("full_name") or user.email.split("@")[0].capitalize()
first_name = display_name.split()[0] if display_name.split() else display_name

daily_capacity = float(meta.get("daily_capacity", 6.0))

course_prefs = meta.get("course_prefs") or {}
if not isinstance(course_prefs, dict):
    course_prefs = {}

course_info = meta.get("course_info") or {}
if not isinstance(course_info, dict):
    course_info = {}

APP_META_KEYS = [
    "full_name",
    "daily_capacity",
    "exam_spread",
    "assign_spread",
    "course_prefs",
    "course_info",
    "study_plan_text",
    "study_plan_updated_at",
]

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

def greeting() -> str:
    hour = datetime.now(TZ).hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"

def safe_hex(value, fallback: str) -> str:
    if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        return value.upper()
    return fallback

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
    try:
        prior = int(info.get("prior_done") or 0)
    except (TypeError, ValueError):
        prior = 0
    if prior > 0:
        entry["prior_done"] = prior
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
        is_review = "review" in lower or "practice" in lower
        if any(w in lower for w in ["exam", "midterm", "final", "test"]) and not is_review:
            item_type, diff = "exam", 5
        elif "quiz" in lower and not is_review:
            item_type, diff = "quiz", 4
        elif "assignment" in uid or is_review or any(w in lower for w in ["homework", "hw", "project", "lab", "assignment", "paper"]):
            # Canvas gives every assignment a UID like "event-assignment-123", even when the
            # title has no keyword (e.g. "Hawkes Lesson 1.1"). Those are due items, not classes.
            # "Test 3 Review" is homework about a test, not the test itself.
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

def build_local_fallback_plan(upcoming_items: pd.DataFrame, today: pd.Timestamp, cap: float) -> str:
    if upcoming_items.empty:
        return "You have no unfinished tasks due in the next 14 days—enjoy the breathing room!"
    lines = ["*Gemini servers are experiencing high demand, so here is an auto-balanced plan built directly from your deadlines:*\n"]
    sorted_tasks = upcoming_items.sort_values(["date", "difficulty"], ascending=[True, False])
    for i in range(7):
        day = today + pd.Timedelta(days=i)
        day_tasks = sorted_tasks[sorted_tasks["date"].dt.normalize() >= day].head(2)
        if not day_tasks.empty:
            bullets = ", ".join(
                f"**{r['course']}** ({r['title']} — {min(r['hours'], round(cap / 2, 1))}h)"
                for _, r in day_tasks.iterrows()
            )
            lines.append(f"- **{day.strftime('%a %b %d')}:** Focus on {bullets}")
    return "\n".join(lines)

def generate_study_plan_text(
    upcoming_items: pd.DataFrame,
    peak_days: pd.DataFrame,
    student_name: str,
    cap: float,
    today: pd.Timestamp,
) -> str:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    items_summary = upcoming_items[["course", "date", "title", "type", "hours", "difficulty"]].copy()
    if not items_summary.empty:
        items_summary["date"] = items_summary["date"].dt.strftime("%Y-%m-%d")
    peaks_summary = peak_days[["date", "level"]].copy()
    if not peaks_summary.empty:
        peaks_summary["date"] = peaks_summary["date"].dt.strftime("%Y-%m-%d")

    prompt = f"""
    You are an academic coach for {student_name}. Today is {today.strftime('%Y-%m-%d')}.
    Daily capacity: {cap}h/day.
    Busy and peak days (from what is due): {peaks_summary.to_dict(orient="records")}
    Tasks (next 14 days): {items_summary.to_dict(orient="records")}

    Write a concise, bulleted 7-day study plan to flatten peak crunch days. Name exact courses, tasks, and realistic hour blocks within {cap}h/day. Keep it brief and scannable.
    """
    cfg = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        max_output_tokens=700,
    )

    for model_name in MODEL_FALLBACKS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=cfg,
            )
            if response.text and response.text.strip():
                return response.text.strip()
        except Exception as e:
            err_str = str(e)
            if any(code in err_str for code in ["503", "429", "404", "UNAVAILABLE", "NOT_FOUND", "RESOURCE_EXHAUSTED"]):
                time.sleep(0.8)
                continue
            raise

    return build_local_fallback_plan(upcoming_items, today, cap)

def start_background_study_plan(
    uid: str,
    access_token: str,
    refresh_token: str,
    current_meta: dict,
    df: pd.DataFrame,
    load_df: pd.DataFrame,
    student_name: str,
    cap: float,
):
    today = pd.Timestamp.now().normalize()
    upcoming_items = df[(df["done"] == "no") & (df["date"] >= today) & (df["date"] <= today + pd.Timedelta(days=14))].copy()
    peak_days = load_df[(load_df["date"] >= today) & (load_df["date"] <= today + pd.Timedelta(days=14)) & (load_df["level"].isin(["busy", "peak"]))].copy()

    STUDY_PLAN_JOBS[uid] = {
        "status": "running",
        "started_at": datetime.now(ZoneInfo("America/New_York")).strftime("%I:%M %p"),
        "plan": None,
        "error": None,
    }

    def _worker():
        try:
            plan_text = generate_study_plan_text(upcoming_items, peak_days, student_name, cap, today)
            updated_at = datetime.now(ZoneInfo("America/New_York")).strftime("%b %d at %I:%M %p")

            # Persist directly to Supabase so it survives closing/reopening any browser
            bg_supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
            bg_supabase.auth.set_session(access_token, refresh_token)
            saved_meta = {k: current_meta.get(k) for k in APP_META_KEYS if current_meta.get(k) is not None}
            saved_meta["study_plan_text"] = plan_text
            saved_meta["study_plan_updated_at"] = updated_at
            bg_supabase.auth.update_user({"data": saved_meta})

            STUDY_PLAN_JOBS[uid] = {
                "status": "done",
                "updated_at": updated_at,
                "plan": plan_text,
                "error": None,
            }
        except Exception as exc:
            STUDY_PLAN_JOBS[uid] = {
                "status": "error",
                "plan": None,
                "error": str(exc),
            }

    threading.Thread(target=_worker, daemon=True).start()


# ---------- Load data ----------
df = load_user_df()
now_local = datetime.now(TZ)
today_local = pd.Timestamp(now_local.date())
HAS_DATA = not df.empty

# ---------- Class colors: blue, indigo, violet, pink, teal (never the busyness colors) ----------
COURSE_PALETTE = ["#3C8BD0", "#727DD3", "#9970C4", "#BF6291", "#2D95A7", "#5E6E8C"]
NEUTRAL_COURSE = "#8A8F9C"
NON_CLASSES = {"General", "Life", "Work", "Personal"}

all_courses = sorted(df["course"].unique().tolist()) if HAS_DATA else []
_real_courses = [c for c in all_courses if c not in NON_CLASSES]

def course_color(course: str) -> str:
    if course in _real_courses:
        auto = COURSE_PALETTE[_real_courses.index(course) % len(COURSE_PALETTE)]
    else:
        auto = NEUTRAL_COURSE
    pref = course_prefs.get(course) or {}
    if pref.get("custom"):
        return safe_hex(pref.get("color"), auto)
    return auto

def code_chip(course: str) -> str:
    c = course_color(course)
    return (
        f'<span class="code-chip" style="background:color-mix(in srgb, {c} 13%, white); '
        f'color:color-mix(in srgb, {c} 72%, #15171C);"><i class="course-dot" style="background:{c};"></i>{esc(course)}</span>'
    )

def level_chip(level: str, text: str | None = None, size: int = 14) -> str:
    label = text if text is not None else f"{wx.name(level)} · {level}"
    return f'<span class="level-chip" data-level="{level}">{wx.icon(level, size)}{esc(label)}</span>'

# ---------- Class filter (shared by Home, Semester, Calendar and Tasks) ----------
if "course_filter" not in st.session_state:
    st.session_state["course_filter"] = []

def _course_filter_changed():
    st.session_state["course_filter"] = list(st.session_state.get("_course_filter_w") or [])

selected_courses = [c for c in st.session_state["course_filter"] if c in all_courses] or all_courses

def class_filter_control():
    if not HAS_DATA:
        return
    label = "All classes" if len(selected_courses) == len(all_courses) else f"{len(selected_courses)} of {len(all_courses)} classes"
    with st.popover(label, icon=":material/tune:", use_container_width=True):
        st.session_state["_course_filter_w"] = selected_courses if len(selected_courses) < len(all_courses) else []
        st.pills(
            "Show only these classes", all_courses, selection_mode="multi",
            key="_course_filter_w", on_change=_course_filter_changed,
        )
        st.caption("Pick none to see everything.")

filtered_df = df[df["course"].isin(selected_courses)].copy() if HAS_DATA else df

# ---------- Class progress (graded work + work finished before the calendar feed) ----------
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
    try:
        prior_done = max(int(info.get("prior_done") or 0), 0)
    except (TypeError, ValueError):
        prior_done = 0

    calendar_done = int(is_done.sum())
    total = max(on_calendar + prior_done, expected)
    done = min(calendar_done + prior_done, total)
    not_posted = max(total - on_calendar - prior_done, 0)

    past_due_mask = (dates < today_local) & ~is_done
    ahead_on_calendar = int(((dates >= today_local) & ~is_done).sum())

    start = dates.min()
    end = dates.max()
    end_source = "last item on your calendar"
    if info.get("end"):
        parsed_end = pd.to_datetime(info["end"], errors="coerce")
        if pd.notna(parsed_end) and parsed_end.normalize() >= end:
            end = parsed_end.normalize()
            end_source = "last day of class"
    span_days = (end - start).days
    elapsed = None if span_days <= 0 else round(min(max((today_local - start).days / span_days, 0), 1) * 100)

    return {
        "pct": round(done / total * 100) if total else 0,
        "done": done,
        "calendar_done": calendar_done,
        "prior_done": prior_done,
        "total": total,
        "ahead": ahead_on_calendar + not_posted,
        "past_due": int(past_due_mask.sum()),
        "not_posted": not_posted,
        "start": start,
        "end": end,
        "end_source": end_source,
        "elapsed": elapsed,
        "past_due_ids": graded.loc[past_due_mask, "id"].astype(int).tolist(),
        "past_due_df": graded.loc[past_due_mask, ["date", "title", "type"]].sort_values("date"),
    }

progress = {}
for _course in all_courses:
    _p = course_progress(df[df["course"] == _course], course_info.get(_course) or {})
    if _p:
        progress[_course] = _p

sel_progress = {c: progress[c] for c in selected_courses if c in progress}
total_items = sum(p["total"] for p in sel_progress.values())
done_items = sum(p["done"] for p in sel_progress.values())
overall_pct = round((done_items / total_items) * 100) if total_items else 0

# ---------- Busyness: what's DUE each day (see busyness.py). No spreading, no hours or difficulty ----------
if HAS_DATA:
    range_start = min(filtered_df["date"].min(), today_local)
    range_end = max(filtered_df["date"].max(), today_local)
    daily_df = bz.daily_scores(filtered_df[["date", "course", "type"]], range_start, range_end)
    weekly_df = bz.weekly_scores(daily_df)
    course_daily_df = bz.course_daily_scores(filtered_df[["date", "course", "type"]])
    level_by_day = dict(zip(daily_df["date"], daily_df["level"]))
    count_by_day = dict(zip(daily_df["date"], daily_df["count"]))
else:
    daily_df = weekly_df = course_daily_df = pd.DataFrame()
    level_by_day, count_by_day = {}, {}

def level_on(day) -> str:
    return level_by_day.get(pd.Timestamp(day).normalize(), "open")

# Grade stakes as dot size. Until grade weights are stored per item, the item type stands in:
# exams are big, quizzes medium, everything else small. Dot size = the biggest single item.
STAKE_RANK = {"exam": 3, "quiz": 2}

def stake_rank(types) -> int:
    return max((STAKE_RANK.get(t, 1) for t in types), default=1)

def short_label(row) -> str:
    title = str(row["title"])
    title = title if len(title) <= 26 else title[:25] + "…"
    return f"{row['course']} {title}"

def items_between(start, end) -> pd.DataFrame:
    sub = filtered_df[(filtered_df["date"] >= start) & (filtered_df["date"] <= end)].copy()
    if sub.empty:
        return sub
    sub["w"] = sub["type"].map(lambda t: bz.TYPE_WEIGHTS.get(t, bz.DEFAULT_WEIGHT))
    return sub[sub["w"] > 0].sort_values(["w", "date"], ascending=[False, True])

def top_items(start, end, n=3) -> list[str]:
    """The heaviest items due between start and end (inclusive), for labels and hovers."""
    return [short_label(r) for _, r in items_between(start, end).head(n).iterrows()]

def fmt_range(a, b) -> str:
    return f"{a.strftime('%b %-d')}–{b.strftime('%-d')}" if a.month == b.month else f"{a.strftime('%b %-d')}–{b.strftime('%b %-d')}"

def relative_day(day, weekday: bool = True) -> str:
    delta = (pd.Timestamp(day).normalize() - today_local).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    if delta == -1:
        return "Yesterday"
    if 1 < delta < 7 and weekday:
        return pd.Timestamp(day).strftime("%A")
    if delta > 1:
        return f"in {delta} days"
    if delta >= 7:
        return f"in {delta} days"
    return f"{-delta} days ago"

def semester_figure(view: str, height: int = 340) -> go.Figure:
    """The hero graph: one line for the whole semester, dots colored by busyness, sized by stakes."""
    if view == "Weeks":
        data = weekly_df.rename(columns={"week_start": "x"}).copy()
        data["end"] = data["week_end"]
        data["is_past"] = data["week_end"] < today_local
        title_fmt = [f"Week of {fmt_range(a, b)}" for a, b in zip(data["x"], data["end"])]
        base = 9
    else:
        data = daily_df.rename(columns={"date": "x"}).copy()
        data["end"] = data["x"]
        data["is_past"] = data["x"] < today_local
        title_fmt = [x.strftime("%a %b %-d") for x in data["x"]]
        base = 6 if view == "Days" else 8

    ranks = []
    for a, b in zip(data["x"], data["end"]):
        ranks.append(stake_rank(filtered_df.loc[(filtered_df["date"] >= a) & (filtered_df["date"] <= b), "type"]))
    data["stake"] = ranks
    data["hover"] = [
        f"<b>{t}</b> · {wx.name(lvl)}<br>{cnt} due<br>" + "<br>".join(top_items(a, b))
        for t, lvl, cnt, a, b in zip(title_fmt, data["level"], data["count"], data["x"], data["end"])
    ]

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
            line=dict(color="#15171C", width=2.5 if view != "Days" else 2, shape="spline", smoothing=0.5),
            fill="tozeroy", fillcolor="rgba(21,23,28,0.04)",
            opacity=opacity, hoverinfo="skip", showlegend=False,
        ))
    dots = data[data["level"] != "open"]
    fig.add_trace(go.Scatter(
        x=dots["x"], y=dots["score"], mode="markers",
        marker=dict(
            size=[base * {1: 1.0, 2: 1.45, 3: 2.0}[s] for s in dots["stake"]],
            color=[bz.LEVEL_FILL[l] for l in dots["level"]],
            line=dict(width=1.5, color=[bz.LEVEL_INK[l] for l in dots["level"]]),
            opacity=[0.45 if p else 1.0 for p in dots["is_past"]],
        ),
        hovertext=dots["hover"], hoverinfo="text", showlegend=False,
    ))
    # Peaks get labeled by their cause, so the hardest stretches explain themselves.
    if view in ("Weeks", "Month"):
        for _, r in data[data["level"] == "peak"].iterrows():
            cause = top_items(r["x"], r["end"], 1)
            if cause:
                fig.add_annotation(
                    x=r["x"], y=r["score"], text=cause[0], showarrow=False, yshift=22,
                    font=dict(size=11, color=bz.LEVEL_INK["peak"], family=CHART_FONT),
                    bgcolor="#fff0ec", borderpad=4,
                )
    # Today
    fig.add_vline(x=today_local, line_dash="dash", line_color="#15171C", line_width=1.2)
    fig.add_annotation(
        x=today_local, y=1.03, yref="paper", text="TODAY", showarrow=False,
        font=dict(size=10, color="#FFFFFF", family=CHART_FONT), bgcolor="#15171C", borderpad=3,
    )
    ymax = max(data["score"].max(), 1) * 1.32
    xaxis = dict(showgrid=False, showline=False, tickformat="%b", dtick="M1", ticklabelmode="period",
                 tickfont=dict(color="#686D7A", size=12), fixedrange=view != "Month")
    if view == "Month":
        xaxis.update(range=[today_local - pd.Timedelta(days=9), today_local + pd.Timedelta(days=24)],
                     tickformat="%b %-d", dtick=7 * 24 * 3600 * 1000, ticklabelmode="instant")
    fig.update_layout(
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        height=height, margin=dict(l=4, r=4, t=28, b=8),
        xaxis=xaxis,
        yaxis=dict(visible=False, range=[0, ymax], fixedrange=True),
        dragmode="pan" if view == "Month" else False,
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#E6E3DD", font=dict(color="#15171C", family=CHART_FONT)),
        font=dict(family=CHART_FONT),
    )
    return fig

def legend_html(show_stakes: bool = True) -> str:
    parts = [
        f'<span><i style="background:{bz.LEVEL_FILL[l]}; border:1px solid {bz.LEVEL_INK[l]};"></i>{wx.icon(l, 15)}{l.capitalize()}</span>'
        for l in bz.LEVELS if l != "open"
    ]
    if show_stakes:
        parts.append('<span class="sep"></span>')
        parts.append('<span class="dot-key"><b style="width:6px;height:6px;"></b><b style="width:9px;height:9px;"></b><b style="width:12px;height:12px;"></b>&nbsp;Bigger dot = exam or quiz</span>')
    return f'<div class="legend">{"".join(parts)}</div>'

# ---------- Shared page pieces ----------
def page_header(eyebrow: str, title: str, sub: str | None = None, controls=None, ratio=(3, 1.15)):
    if controls is None:
        render_html(
            f'<div class="page-head"><div class="eyebrow">{eyebrow}</div><div class="page-title">{title}</div>'
            + (f'<div class="page-sub">{sub}</div>' if sub else "") + "</div>"
        )
        return
    left, right = st.columns(list(ratio), vertical_alignment="bottom")
    with left:
        render_html(
            f'<div class="page-head"><div class="eyebrow">{eyebrow}</div><div class="page-title">{title}</div>'
            + (f'<div class="page-sub">{sub}</div>' if sub else "") + "</div>"
        )
    with right:
        controls()

def empty_state(eyebrow: str):
    page_header(eyebrow, "Your semester is empty.", "Add your Canvas calendar or a syllabus and this fills in with every due date, exam and quiz.")
    st.page_link(PAGES["add"], label="Add your classes", icon=":material/add_circle:")

def set_done(item_id: int, key: str):
    value = bool(st.session_state.get(key))
    try:
        supabase.table("items").update({"done": "yes" if value else "no"}).eq("id", int(item_id)).execute()
    except Exception as e:
        flash(f"Couldn't save that check-off: {e}", "error")

def item_checkbox(row, key_prefix: str, show_date: bool = False):
    """One task: a real checkbox on the left, its class chip and type on the right."""
    key = f"{key_prefix}_{int(row['id'])}"
    c1, c2 = st.columns([4.2, 1.6], vertical_alignment="center", gap="small")
    with c1:
        label = str(row["title"]).replace("[", "(").replace("]", ")")
        if show_date:
            label += f"  ·  :gray[{row['date'].strftime('%a %b %-d')}]"
        st.checkbox(label, value=row["done"] == "yes", key=key, on_change=set_done, args=(int(row["id"]), key))
    with c2:
        t = str(row["type"])
        render_html(
            f'<div class="item-row item-meta" style="justify-content:flex-end;">'
            f'<span class="type-tag {t}">{esc(type_label(t))}</span>{code_chip(row["course"])}</div>'
        )

def quick_add_form(key: str = "quick_nl_form"):
    with st.form(key, clear_on_submit=True, border=False):
        q1, q2 = st.columns([4, 1.1], vertical_alignment="bottom")
        nl_prompt = q1.text_input(
            "Quick add", placeholder="Quick add: “ECON quiz Fri”", label_visibility="collapsed",
        )
        if q2.form_submit_button("Add", use_container_width=True) and nl_prompt.strip():
            try:
                parsed = parse_quick_natural_language(nl_prompt.strip())
                added, _ = add_rows_dedup(parsed)
                flash(f"Added {added} item{'s' if added != 1 else ''}.")
                st.rerun()
            except Exception as e:
                st.error(f"Couldn't add that: {e}")

# ---------- Today's brief (rules for now; AI-written later, within the same shape) ----------
def build_brief():
    today_level = level_on(today_local)
    open_today = filtered_df[(filtered_df["date"].dt.normalize() == today_local)]
    open_today = open_today[open_today["type"].map(lambda t: bz.TYPE_WEIGHTS.get(t, bz.DEFAULT_WEIGHT) > 0).astype(bool)]
    left_today = open_today[open_today["done"] == "no"]

    tomorrow = today_local + pd.Timedelta(days=1)
    t_level = level_on(tomorrow)
    t_count = count_by_day.get(tomorrow, 0)

    # Headline
    if open_today.empty:
        head = "Nothing due today."
    elif left_today.empty:
        head = "Today's list is done."
    else:
        n = len(left_today)
        head = f"{n} thing{'s' if n != 1 else ''} due today."

    lines = [wx.WEATHER[today_level]["line"]]
    if t_count:
        lines.append(f"Tomorrow: <b>{t_count} due</b> ({wx.name(t_level).lower()}).")
    else:
        lines.append("Tomorrow is clear.")

    # Heads-up: the next busy or peak day after the next three days, within two weeks.
    window = daily_df[(daily_df["date"] > today_local + pd.Timedelta(days=3)) &
                      (daily_df["date"] <= today_local + pd.Timedelta(days=14)) &
                      (daily_df["level"].isin(["busy", "peak"]))]
    heads_up = None
    if not window.empty:
        r = window.sort_values(["score", "date"], ascending=[False, True]).iloc[0]
        cause = items_between(r["date"], r["date"])
        top = cause.iloc[0] if not cause.empty else None
        others = len(cause) - 1
        what = f"{esc(top['course'])} {esc(top['title'])}" if top is not None else "a lot"
        if others > 0:
            what += f" + {others} more"
        heads_up = (r["level"], f"<b>{r['date'].strftime('%A, %b %-d')}</b> looks like a {wx.name(r['level']).lower()} day: {what}. That's {(r['date'] - today_local).days} days out.")
    return today_level, head, " ".join(lines), open_today.sort_values(["done", "type"]), heads_up

def render_brief():
    today_level, head, text, today_items, heads_up = build_brief()
    dark = " dark" if wx.is_dark(today_level) else ""
    with st.container(key="brief"):
        render_html(
            f'<div class="sky-wrap">{wx.sky(today_level)}'
            f'<div class="sky-chip{dark}">{wx.icon(today_level, 18)}{wx.name(today_level)} today</div></div>'
        )
        render_html(
            f'<div class="eyebrow" style="margin-top:18px;">Today\'s brief · {now_local.strftime("%A, %B %-d")}</div>'
            f'<div class="brief-head" style="margin-top:0;">{esc(head)}</div><div class="brief-text">{text}</div>'
        )

        if not today_items.empty:
            render_html('<div class="brief-section">Due today</div>')
            for _, r in today_items.head(5).iterrows():
                item_checkbox(r, "brief")
            if len(today_items) > 5:
                st.page_link(PAGES["tasks"], label=f"{len(today_items) - 5} more today in Tasks", icon=":material/arrow_forward:")

        upcoming = filtered_df[(filtered_df["date"] > today_local) & (filtered_df["date"] <= today_local + pd.Timedelta(days=3))
                               & (filtered_df["done"] == "no")]
        upcoming = upcoming[upcoming["type"].map(lambda t: bz.TYPE_WEIGHTS.get(t, bz.DEFAULT_WEIGHT) > 0).astype(bool)]
        render_html('<div class="brief-section">Next three days</div>')
        if upcoming.empty:
            render_html('<div class="empty-note">Nothing due. Enjoy the open stretch.</div>')
        else:
            upcoming = upcoming.assign(w=upcoming["type"].map(lambda t: bz.TYPE_WEIGHTS.get(t, bz.DEFAULT_WEIGHT)))
            rows = []
            for day, grp in upcoming.groupby(upcoming["date"].dt.normalize()):
                grp = grp.sort_values("w", ascending=False)
                first = grp.iloc[0]
                more = f'<span class="item-when">+{len(grp) - 1} more</span>' if len(grp) > 1 else ""
                rows.append(
                    f'<div class="item-row"><span class="item-when" style="width:84px;">{relative_day(day)}</span>'
                    f'{level_chip(level_on(day), str(count_by_day.get(day, len(grp))) + " due", 13)}'
                    f'<span class="item-title">{esc(first["title"])}</span>{more}{code_chip(first["course"])}</div>'
                )
            render_html('<div style="display:flex; flex-direction:column; gap:8px;">' + "".join(rows) + "</div>")

        if heads_up:
            lvl, msg = heads_up
            render_html(f'<div class="brief-section">Heads up</div><div class="heads-up" data-level="{lvl}">{wx.icon(lvl, 20)}<div>{msg}</div></div>')

def render_progress_card():
    with st.container(key="progress"):
        render_html(
            f'<div class="card-label">Coursework done</div>'
            f'<div class="big-num" style="margin-top:8px;">{overall_pct}<small>%</small></div>'
            f'<div class="muted" style="font-size:0.84rem; margin-top:4px;">{done_items} of {total_items} graded items</div>'
        )
        bars = []
        for c, p in sel_progress.items():
            col = course_color(c)
            bars.append(
                f'<div class="bar-row"><div class="bar-top"><span style="display:inline-flex; align-items:center; gap:7px;">'
                f'<i class="course-dot" style="background:{col};"></i>{esc(c)}</span><span>{p["pct"]}%</span></div>'
                f'<div class="bar"><i style="width:{p["pct"]}%; background:{col};"></i></div></div>'
            )
        render_html("".join(bars))
        st.page_link(PAGES["classes"], label="See every class", icon=":material/arrow_forward:")

def week_strip_html() -> str:
    week_start = today_local - pd.Timedelta(days=today_local.weekday())
    cells = []
    for i in range(7):
        day = week_start + pd.Timedelta(days=i)
        lvl = level_on(day)
        cnt = count_by_day.get(day, 0)
        cls = "day-cell" + (" today" if day == today_local else "") + (" past" if day < today_local else "")
        meta_txt = f"{cnt} due · {wx.name(lvl)}" if cnt else wx.name(lvl)
        cells.append(
            f'<div class="{cls}" data-level="{lvl}"><div class="day-top"><span class="day-name">{day.strftime("%a")}</span>'
            f'{wx.icon(lvl, 18)}</div><div class="day-num">{day.day}</div><div class="day-meta">{meta_txt}</div></div>'
        )
    return f'<div class="week-strip">{"".join(cells)}</div>'

def home_headline() -> tuple[str, str]:
    """One line that makes the aha land: where the semester gets hard, and how far away it is."""
    ahead = weekly_df[weekly_df["week_end"] >= today_local]
    if ahead.empty:
        return "That's a wrap on the semester.", "Everything on your calendar is behind you."
    hardest = ahead.loc[ahead["score"].idxmax()]
    rng = fmt_range(hardest["week_start"], hardest["week_end"])
    cause = top_items(hardest["week_start"], hardest["week_end"], 1)
    cause_txt = f" <b>{esc(cause[0])}</b> lands then." if cause else ""
    if hardest["week_start"] <= today_local <= hardest["week_end"]:
        return "You're in your hardest week left.", f"This week ({rng}) is the peak of what's ahead.{cause_txt}"
    if hardest["level"] in ("busy", "peak"):
        days_out = (hardest["week_start"] - today_local).days
        return f"Your hardest week left is {rng}.", f"It starts in {days_out} day{'s' if days_out != 1 else ''}.{cause_txt}"
    return "Smooth weather ahead.", "No busy weeks left on your calendar."

# ---------- Pages ----------
def page_home():
    show_flash()
    if not HAS_DATA:
        empty_state(f"{greeting()}, {esc(first_name)}")
        return
    title, sub = home_headline()

    def controls():
        quick_add_form()
        class_filter_control()

    page_header(f"{greeting()}, {esc(first_name)} · {now_local.strftime('%A, %B %-d')}", esc(title), sub, controls)

    # 1. The hero: the whole semester as one line
    if not st.session_state.get("_revealed"):
        st.html(
            "<style>.st-key-hero .js-line{stroke-dasharray:6000;stroke-dashoffset:6000;"
            "animation:draw-line 2.2s cubic-bezier(0.22,1,0.36,1) .15s forwards}"
            ".st-key-hero .scatterlayer .trace:last-child .point{opacity:0;animation:rise-in .5s ease-out 1.7s forwards}</style>"
        )
        st.session_state["_revealed"] = True
    with st.container(key="hero"):
        h_left, h_right = st.columns([4, 1.25], vertical_alignment="center")
        with h_left:
            render_html('<div class="hero-head"><span class="hero-title">Your semester</span>'
                        '<span class="muted" style="font-size:0.85rem;">How busy each week is, from what\'s due</span></div>')
        with h_right:
            view = st.segmented_control(
                "Zoom", ["Semester", "Month"], default="Semester", label_visibility="collapsed", key="hero_zoom",
            ) or "Semester"
        fig_view = "Weeks" if view == "Semester" else "Month"
        st.plotly_chart(
            semester_figure(fig_view, height=360), use_container_width=True,
            config={"displayModeBar": False, "scrollZoom": fig_view == "Month"},
        )
        if fig_view == "Month":
            st.caption("Drag the graph to move through the semester.")
        render_html(legend_html())

    # 2. This week, one cell per day
    render_html(week_strip_html())

    # 3. Today's brief (the old "My Schedule" spot) and progress
    b_left, b_right = st.columns([2.6, 1], gap="medium")
    with b_left:
        render_brief()
    with b_right:
        render_progress_card()

def page_semester():
    if not HAS_DATA:
        empty_state("Semester")
        return
    page_header(
        "Semester", "The whole semester, one line.",
        "Every dot is a day or week with something due. Bigger dots are exams and quizzes.",
        class_filter_control,
    )
    with st.container(key="hero"):
        mode = st.segmented_control("View", ["Weeks", "Days", "By class"], default="Weeks", label_visibility="collapsed", key="sem_view") or "Weeks"
        if mode in ("Weeks", "Days"):
            st.plotly_chart(semester_figure(mode, height=460), use_container_width=True, config={"displayModeBar": False})
            render_html(legend_html())
        else:
            fig_stack = px.area(
                course_daily_df, x="date", y="score", color="course",
                color_discrete_map={c: course_color(c) for c in course_daily_df["course"].unique()},
            )
            fig_stack.update_layout(
                paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF", height=460, margin=dict(l=4, r=4, t=10, b=8),
                yaxis=dict(visible=False), xaxis=dict(title=None, showgrid=False), legend_title_text="",
                font=dict(family=CHART_FONT),
            )
            st.plotly_chart(fig_stack, use_container_width=True, config={"displayModeBar": False})
            st.caption("Each class's share of the load. Class colors are labels only.")

    st.write("")
    w_left, w_right = st.columns([1.6, 1], gap="large")
    with w_left:
        render_html('<div class="section-title">Heaviest weeks</div><div class="section-sub">Ranked by what\'s due. Past weeks are faded.</div>')
        top = weekly_df.sort_values("score", ascending=False).head(5)
        rows = []
        for i, (_, r) in enumerate(top.iterrows(), start=1):
            cause = top_items(r["week_start"], r["week_end"], 2)
            fade = ' style="opacity:0.5;"' if r["week_end"] < today_local else ""
            rows.append(
                f'<div class="rank-row"{fade}><span class="rank-n">{i}</span><span class="rank-when">{fmt_range(r["week_start"], r["week_end"])}</span>'
                f'<span>{level_chip(r["level"], str(int(r["count"])) + " due", 13)}</span><span class="rank-cause">{esc(" · ".join(cause))}</span></div>'
            )
        render_html('<div class="card">' + "".join(rows) + "</div>")
    with w_right:
        render_html('<div class="section-title">How busyness works</div><div class="section-sub">Counted on the day things are due.</div>')
        render_html(
            '<div class="card" style="font-size:0.9rem; color:var(--ink-2); line-height:1.6;">'
            'Exams count most, then quizzes, then assignments. Class meetings don\'t count. '
            'Lots of small things from one class on one day count as one heavy day, so a 20-item homework dump '
            'doesn\'t drown out an exam.<div style="height:10px;"></div>'
            + "".join(f'<div style="margin:4px 0;">{level_chip(l, wx.name(l) + " · " + l)}</div>' for l in bz.LEVELS)
            + "</div>"
        )

def page_calendar():
    if not HAS_DATA:
        empty_state("Calendar")
        return
    page_header(
        "Calendar", "Month by month.",
        "Only busy and stormy days get color, so the hard ones jump out. Dots are your classes.",
        class_filter_control,
    )
    tints = {"calm": "#e8f9eb", "steady": "#f9f3e1", "busy": "#fff0e6", "peak": "#fff0ec"}
    cal_events = []
    for _, r in daily_df[daily_df["level"].isin(["busy", "peak"])].iterrows():
        cal_events.append({
            "start": r["date"].strftime("%Y-%m-%d"), "end": r["date"].strftime("%Y-%m-%d"),
            "display": "background", "backgroundColor": tints[r["level"]],
        })
    for _, r in filtered_df.iterrows():
        done = r["done"] == "yes"
        color = "#B5B9C2" if done else course_color(r["course"])
        cal_events.append({
            "title": f"{r['course']} · {r['title']}",
            "start": r["date"].strftime("%Y-%m-%d"),
            "end": r["date"].strftime("%Y-%m-%d"),
            "backgroundColor": color, "borderColor": color,
            "textColor": "#8A8F9C" if done else "#15171C",
        })
    with st.container(key="card"):
        calendar(
            events=cal_events,
            options={
                "initialView": "dayGridMonth", "height": 780, "eventDisplay": "list-item", "dayMaxEvents": 4,
                "headerToolbar": {"left": "title", "center": "", "right": "today prev,next dayGridMonth,listMonth"},
                "buttonText": {"today": "Today", "month": "Month", "list": "List"},
            },
            custom_css="""
                @import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700&family=Plus+Jakarta+Sans:wght@500;600;700&display=swap');
                .fc { font-family: 'Plus Jakarta Sans', sans-serif; color: #15171C; }
                .fc .fc-toolbar-title { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 700; font-size: 1.5rem; }
                .fc .fc-button { background: #FFFFFF; border: 1px solid #E6E3DD; color: #464B57; border-radius: 999px; font-weight: 600; text-transform: none; box-shadow: none; }
                .fc .fc-button-primary:not(:disabled).fc-button-active, .fc .fc-button-primary:not(:disabled):active { background: #15171C; color: #fff; border-color: #15171C; }
                .fc-theme-standard td, .fc-theme-standard th, .fc-theme-standard .fc-scrollgrid { border-color: #EEECE7; }
                .fc .fc-col-header-cell-cushion { color: #686D7A; font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase; font-weight: 700; }
                .fc .fc-daygrid-day-number { color: #464B57; font-weight: 600; font-size: 0.82rem; }
                .fc .fc-day-today { background: transparent !important; }
                .fc .fc-day-today .fc-daygrid-day-number { background: #15171C; color: #fff; border-radius: 999px; padding: 2px 7px; margin: 3px; }
                .fc .fc-bg-event { opacity: 1; }
                .fc-daygrid-dot-event .fc-event-title { font-weight: 600; font-size: 0.76rem; }
                .fc-daygrid-event-dot { border-width: 4px; }
            """,
            key="full_cal_grid",
        )
    render_html('<div class="legend">' + "".join(
        f'<span><i style="background:{bz.LEVEL_FILL[l]}; border:1px solid {bz.LEVEL_INK[l]};"></i>{wx.icon(l, 15)}{wx.name(l)} day</span>'
        for l in ("busy", "peak")) + "</div>")

def page_tasks():
    show_flash()
    if not HAS_DATA:
        empty_state("Tasks")
        return
    due_like = filtered_df[filtered_df["type"].map(lambda t: bz.TYPE_WEIGHTS.get(t, bz.DEFAULT_WEIGHT) > 0).astype(bool)]
    week_end = today_local + pd.Timedelta(days=6 - today_local.weekday())
    left_week = int(((due_like["date"] >= today_local) & (due_like["date"] <= week_end) & (due_like["done"] == "no")).sum())
    past_due = int(((due_like["date"] < today_local) & (due_like["done"] == "no")).sum())
    sub = f"<b>{left_week}</b> left this week"
    if past_due:
        sub += f" · <b>{past_due}</b> past due and not checked off"
    page_header("Tasks", "Everything that's due.", sub, class_filter_control)

    f1, f2, f3 = st.columns([3.2, 1.6, 1], vertical_alignment="center")
    with f1:
        window = st.segmented_control(
            "Show", ["This week", "Next 2 weeks", "Upcoming", "Past due", "Done", "All"],
            default="Next 2 weeks", label_visibility="collapsed", key="task_window",
        ) or "Next 2 weeks"
    with f2:
        query = st.text_input("Search", placeholder="Search tasks", label_visibility="collapsed", key="task_search")
    with f3:
        table_mode = st.toggle("Edit as table", key="task_table")

    d = filtered_df.copy()
    dn = d["date"].dt.normalize()
    if window == "This week":
        d = d[(dn >= today_local) & (dn <= week_end)]
    elif window == "Next 2 weeks":
        d = d[(dn >= today_local) & (dn <= today_local + pd.Timedelta(days=13))]
    elif window == "Upcoming":
        d = d[dn >= today_local]
    elif window == "Past due":
        d = d[(dn < today_local) & (d["done"] == "no")]
    elif window == "Done":
        d = d[d["done"] == "yes"]
    if query.strip():
        q = query.strip().lower()
        d = d[d["title"].str.lower().str.contains(q, regex=False) | d["course"].str.lower().str.contains(q, regex=False)]
    if not table_mode:
        d = d[d["type"] != "recurring"]  # class meetings live on the calendar, not the to-do list
    d = d.sort_values(["date", "course", "title"], ascending=[window != "Done", True, True])

    if d.empty:
        render_html('<div class="card"><div class="empty-note">Nothing here. Try a wider range or clear the search.</div></div>')
        return

    if table_mode:
        edit_df = d[["id", "done", "date", "course", "title", "type", "hours", "difficulty"]].copy()
        edit_df["done"] = edit_df["done"] == "yes"
        edit_df["date"] = edit_df["date"].dt.date
        edit_df["Delete"] = False
        edited = st.data_editor(
            edit_df, hide_index=True, use_container_width=True, disabled=["id"], height=min(640, 38 + 35 * len(edit_df)),
            column_config={
                "id": None,
                "done": st.column_config.CheckboxColumn("Done", width="small"),
                "date": st.column_config.DateColumn("Due", format="ddd, MMM D", width="small"),
                "course": st.column_config.SelectboxColumn("Class", options=sorted(set(all_courses) | {"General"}), width="small"),
                "title": st.column_config.TextColumn("Task", width="large"),
                "type": st.column_config.SelectboxColumn("Type", options=TYPE_OPTIONS, width="small"),
                "hours": st.column_config.NumberColumn("Hours", min_value=0.25, max_value=40.0, step=0.25, width="small", help="Used by Study coach only"),
                "difficulty": st.column_config.NumberColumn("Effort", min_value=1, max_value=5, step=1, width="small", help="1 easy to 5 hard. Used by Study coach only"),
                "Delete": st.column_config.CheckboxColumn("Delete", width="small"),
            },
            key="master_editor",
        )
        if st.button("Save changes", type="primary"):
            orig_by_id = edit_df.set_index("id").to_dict(orient="index")
            changed = deleted = 0
            for _, row in edited.iterrows():
                rid = int(row["id"])
                if row["Delete"]:
                    supabase.table("items").delete().eq("id", rid).execute()
                    deleted += 1
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
                    changed += 1
            parts = []
            if changed:
                parts.append(f"updated {changed}")
            if deleted:
                parts.append(f"deleted {deleted}")
            flash(("Saved: " + " and ".join(parts) + ".") if parts else "No changes to save.")
            st.rerun()
        return

    LIMIT = 80
    with st.container(key="tasklist"):
        for day, grp in list(d.groupby(d["date"].dt.normalize(), sort=False))[:LIMIT]:
            lvl = level_on(day)
            render_html(
                f'<div class="day-group"><span class="dg-date">{day.strftime("%a, %b %-d")}<span>{relative_day(day, weekday=False)}</span></span>'
                f'{level_chip(lvl, str(count_by_day.get(day, len(grp))) + " due · " + wx.name(lvl), 13)}</div>'
            )
            grp = grp.assign(w=grp["type"].map(lambda t: bz.TYPE_WEIGHTS.get(t, bz.DEFAULT_WEIGHT)))
            grp = grp.sort_values(["w", "course", "title"], ascending=[False, True, True])
            # The batch rule, in the list too: a pile of small items from one class collapses.
            for course, cgrp in grp.groupby("course", sort=False):
                small = cgrp[cgrp["type"] != "exam"]
                if len(small) <= 4:
                    for _, r in cgrp.iterrows():
                        item_checkbox(r, "task")
                    continue
                for _, r in cgrp[cgrp["type"] == "exam"].iterrows():
                    item_checkbox(r, "task")
                for _, r in small.head(2).iterrows():
                    item_checkbox(r, "task")
                rest = small.iloc[2:]
                left = int((rest["done"] == "no").sum())
                with st.expander(f"{len(rest)} more from {course} · {left} left"):
                    for _, r in rest.iterrows():
                        item_checkbox(r, "task")
    if d["date"].dt.normalize().nunique() > LIMIT:
        st.caption(f"Showing the first {LIMIT} days. Narrow the range to see the rest.")

def page_classes():
    show_flash()
    if not HAS_DATA:
        empty_state("Classes")
        return
    page_header("Classes", "How each class is going.", "Graded work you've checked off, plus anything you finished before your calendar feed starts.")
    tab_prog, tab_totals, tab_edit = st.tabs(["Progress", "Syllabus totals", "Edit classes"])

    with tab_prog:
        if not progress:
            st.info("No graded work yet. Sync Canvas or add assignments, quizzes and exams.")
        else:
            if "General" in progress:
                st.caption("Items under General aren't a real class yet. Sort them in Edit classes or Tasks.")
            cols = st.columns(2, gap="medium")
            for i, (c, p) in enumerate(progress.items()):
                color = course_color(c)
                done_w = (p["done"] / p["total"] * 100) if p["total"] else 0
                late_w = (p["past_due"] / p["total"] * 100) if p["total"] else 0
                elapsed_txt = f'{p["elapsed"]}%' if p["elapsed"] is not None else "n/a"
                span_note = f'{p["start"].strftime("%b %-d")} to {p["end"].strftime("%b %-d")} ({p["end_source"]})'
                if p["prior_done"] > 0:
                    span_note += f' · includes {p["prior_done"]} done before your calendar'
                if p["not_posted"] > 0:
                    span_note += f' · {p["not_posted"]} not posted yet'
                with cols[i % 2]:
                    render_html(
                        f'<div class="card"><div class="class-card-head">{code_chip(c)}<span class="class-card-pct">{p["pct"]}%</span></div>'
                        f'<div class="bar" style="margin-top:12px;"><i style="width:{done_w:.1f}%; background:{color};"></i>'
                        f'<i style="width:{late_w:.1f}%; background:color-mix(in srgb, {color} 30%, white);"></i></div>'
                        f'<div class="stat-grid">'
                        f'<div class="stat-box"><div class="stat-num">{p["done"]}/{p["total"]}</div><div class="stat-label">graded items done</div></div>'
                        f'<div class="stat-box"><div class="stat-num">{p["ahead"]}</div><div class="stat-label">still ahead</div></div>'
                        f'<div class="stat-box"><div class="stat-num">{p["past_due"]}</div><div class="stat-label">past due, not checked</div></div>'
                        f'<div class="stat-box"><div class="stat-num">{elapsed_txt}</div><div class="stat-label">of the class is behind you</div></div>'
                        f'</div><div class="note">{esc(span_note)}</div></div>'
                    )
                    if p["past_due"]:
                        with st.expander(f'{p["past_due"]} past-due in {c}, not checked off'):
                            past_df = p["past_due_df"].copy()
                            past_df["date"] = past_df["date"].dt.strftime("%b %-d")
                            past_df["type"] = past_df["type"].map(type_label)
                            st.dataframe(past_df.rename(columns={"date": "Due", "title": "Task", "type": "Type"}), hide_index=True, use_container_width=True)
                            if st.button(f"Mark all {p['past_due']} done", key=f"markdone_{c}"):
                                try:
                                    supabase.table("items").update({"done": "yes"}).in_("id", p["past_due_ids"]).execute()
                                    flash(f"Marked {p['past_due']} items in {c} done.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Couldn't update those: {e}")

    with tab_totals:
        render_html('<div class="section-sub" style="margin-top:6px;">From your syllabus: how many graded items the whole class has, how many you finished '
                    'before your calendar feed starts, and the last day of class. This keeps your percentages honest.</div>')
        with st.form("course_totals_form"):
            f1, f2, f3, f4 = st.columns([1.6, 2.1, 2.1, 1.8])
            f1.caption("Class")
            f2.caption("Graded items, whole class (0 = not sure)")
            f3.caption("Done before your calendar")
            f4.caption("Last day of class")

            totals_input = {}
            for c in progress:
                info = course_info.get(c) or {}
                existing_end = None
                if info.get("end"):
                    parsed_end = pd.to_datetime(info["end"], errors="coerce")
                    if pd.notna(parsed_end):
                        existing_end = parsed_end.date()

                g1, g2, g3, g4 = st.columns([1.6, 2.1, 2.1, 1.8], vertical_alignment="center")
                with g1:
                    render_html(code_chip(c))
                total_val = g2.number_input(
                    f"Graded items in {c}", min_value=0, max_value=500, value=int(info.get("expected_total") or 0),
                    step=1, key=f"tot_{c}", label_visibility="collapsed",
                )
                prior_val = g3.number_input(
                    f"Already done in {c}", min_value=0, max_value=500, value=int(info.get("prior_done") or 0),
                    step=1, key=f"prior_{c}", label_visibility="collapsed",
                )
                end_val = g4.date_input(
                    f"Last day of class for {c}", value=existing_end, key=f"end_{c}", label_visibility="collapsed",
                )
                totals_input[c] = (int(total_val), int(prior_val), end_val)

            totals_saved = st.form_submit_button("Save totals", type="primary")

        if totals_saved:
            try:
                new_info = dict(course_info)
                for c, (total_val, prior_val, end_val) in totals_input.items():
                    entry = {}
                    if total_val > 0:
                        entry["expected_total"] = total_val
                    if prior_val > 0:
                        entry["prior_done"] = prior_val
                    if end_val:
                        entry["end"] = end_val.strftime("%Y-%m-%d")
                    if entry:
                        new_info[c] = entry
                    else:
                        new_info.pop(c, None)
                save_profile_meta({"course_info": new_info})
                flash("Totals saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Couldn't save totals: {e}")

    with tab_edit:
        render_html('<div class="section-title">Colors</div><div class="section-sub">Class colors are just labels, so they never use the busyness colors. '
                    'Pick your own if you like. Effort is optional and only feeds Study coach.</div>')
        with st.form("course_prefs_form"):
            h1, h2, h3, h4 = st.columns([2, 3, 1.6, 1.2])
            h1.caption("Class")
            h2.caption("Effort (1 easy, 5 hard)")
            h3.caption("Use my own color")
            h4.caption("Color")
            course_avg = df.groupby("course")["difficulty"].mean().to_dict()
            new_prefs = {}
            for c in all_courses:
                pref = course_prefs.get(c) or {}
                default_diff = max(1, min(5, int(pref.get("difficulty", round(course_avg.get(c, 3))))))
                c1, c2, c3, c4 = st.columns([2, 3, 1.6, 1.2], vertical_alignment="center")
                with c1:
                    render_html(code_chip(c))
                diff_val = c2.slider(f"Effort for {c}", 1, 5, default_diff, key=f"pref_diff_{c}", label_visibility="collapsed")
                use_custom = c3.checkbox(f"Use my own color for {c}", value=bool(pref.get("custom", False)), key=f"pref_custom_{c}", label_visibility="collapsed")
                picked = c4.color_picker(f"Color for {c}", value=safe_hex(pref.get("color"), course_color(c)), key=f"pref_color_{c}", label_visibility="collapsed")
                new_prefs[c] = {"difficulty": int(diff_val), "custom": bool(use_custom), "color": picked}
            saved = st.form_submit_button("Save colors", type="primary")
        if saved:
            try:
                save_profile_meta({"course_prefs": {**course_prefs, **new_prefs}})
                flash("Colors saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Couldn't save colors: {e}")
        if course_prefs and st.button("Reset to the default colors"):
            try:
                save_profile_meta({"course_prefs": {}})
                flash("Colors reset.")
                st.rerun()
            except Exception as e:
                st.error(f"Couldn't reset colors: {e}")

        st.divider()
        render_html('<div class="section-title">Rename or merge</div><div class="section-sub">Wrong label? Rename it. Type another class\'s name to merge the two. '
                    'To move one task, change its class in Tasks (Edit as table).</div>')
        rn1, rn2, rn3 = st.columns([2, 2, 1], vertical_alignment="bottom")
        old_name = rn1.selectbox("Class", all_courses, key="rename_old")
        new_name_raw = rn2.text_input("New name", placeholder="e.g., MATH 2171", key="rename_new")
        if rn3.button("Rename", use_container_width=True):
            target = normalize_course(new_name_raw)
            if not new_name_raw.strip():
                st.warning("Type the new name first.")
            elif target == old_name:
                st.info("That's already its name.")
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
                    st.error(f"Couldn't rename: {e}")

        st.divider()
        render_html('<div class="section-title">Delete a class</div><div class="section-sub">Removes the class and every task in it. This can\'t be undone.</div>')
        del1, del2, del3 = st.columns([2, 2, 1], vertical_alignment="bottom")
        del_target = del1.selectbox("Class to delete", all_courses, key="delete_course_select")
        del_task_count = int((df["course"] == del_target).sum())
        confirm_del = del2.checkbox(f"Yes, delete {del_target} and its {del_task_count} task{'s' if del_task_count != 1 else ''}", key="confirm_delete_course")
        if del3.button("Delete", use_container_width=True):
            if not confirm_del:
                st.warning("Tick the box to confirm first.")
            else:
                try:
                    supabase.table("items").delete().eq("user_id", user_id).eq("course", del_target).execute()
                    updated_prefs = dict(course_prefs)
                    updated_prefs.pop(del_target, None)
                    updated_info = dict(course_info)
                    updated_info.pop(del_target, None)
                    save_profile_meta({"course_prefs": updated_prefs, "course_info": updated_info})
                    flash(f"Deleted {del_target} and its {del_task_count} task{'s' if del_task_count != 1 else ''}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Couldn't delete: {e}")

def page_coach():
    if not HAS_DATA:
        empty_state("Study coach")
        return
    page_header(
        "Study coach", "A 7-day plan for what's ahead.",
        f"Built from what's due in the next two weeks and your <b>{daily_capacity:g} hours</b> of study time a day. "
        "It runs in the background, so you can leave this page while it works.",
    )
    job = STUDY_PLAN_JOBS.get(user_id)
    is_running = job is not None and job.get("status") == "running"

    if st.button("Make my 7-day plan", type="primary", disabled=is_running):
        sess = st.session_state["session"]
        start_background_study_plan(
            uid=user_id,
            access_token=sess.access_token,
            refresh_token=sess.refresh_token,
            current_meta=meta,
            df=filtered_df,
            load_df=daily_df,
            student_name=display_name,
            cap=daily_capacity,
        )
        st.rerun()

    if is_running:
        st.info(f"Working on it (started {job.get('started_at')}). Your plan saves automatically, even if you close the tab.")
        time.sleep(2)
        st.rerun()
    elif job is not None and job.get("status") == "error":
        st.error(f"Couldn't make a plan: {job.get('error')}")
    else:
        saved_plan = (job.get("plan") if job and job.get("status") == "done" else None) or meta.get("study_plan_text")
        saved_time = (job.get("updated_at") if job and job.get("status") == "done" else None) or meta.get("study_plan_updated_at")
        if saved_plan:
            with st.container(key="card"):
                if saved_time:
                    st.caption(f"Made {saved_time}")
                st.markdown(saved_plan)

def page_add():
    show_flash()
    page_header("Add & sync", "Bring in your semester.", "Canvas fills in most of it. Syllabi add the exam dates Canvas leaves out.")
    body, _ = st.columns([2.3, 1])
    with body:
        _add_body()

def _add_body():
    render_html('<div class="card-label" style="margin-bottom:6px;">Quick add</div>')
    quick_add_form("quick_nl_form_add")
    st.write("")
    tab_canvas, tab_syl, tab_one = st.tabs(["Canvas calendar", "Syllabus", "One item"])

    with tab_canvas:
        render_html('<div class="section-sub" style="margin-top:6px;">In Canvas, open <b>Calendar</b>, then <b>Calendar Feed</b> (bottom right), and copy the link. '
                    'Canvas only shares about a month of past items, so sync early and often.</div>')
        with st.form("ics_form"):
            ics_link = st.text_input("Canvas calendar link", placeholder="https://…/feeds/calendars/user_….ics")
            days_back = st.number_input(
                "Go back this many days", min_value=7, max_value=365, value=120, step=1,
                help="Far enough to reach your first assignment, so progress counts work you already finished.",
            )
            if st.form_submit_button("Sync Canvas", type="primary") and ics_link:
                try:
                    imported = parse_ics_url(ics_link, int(days_back))
                    added_count, sorted_count = add_rows_dedup(imported)
                    msg = f"Added {added_count} new item{'s' if added_count != 1 else ''}."
                    if sorted_count:
                        msg += f" Sorted {sorted_count} into their classes."
                    flash(msg)
                    st.rerun()
                except Exception as e:
                    st.error(f"Sync didn't work: {e}")

    with tab_syl:
        render_html('<div class="section-sub" style="margin-top:6px;">Upload or paste a syllabus. We pull out every graded item with a date, '
                    'plus the class total and last day, so your progress is accurate.</div>')
        with st.form("syllabus_form"):
            course_tag = st.text_input("Class (optional)", placeholder="e.g., MATH 2171")
            syl_file = st.file_uploader("PDF, Word or a photo", type=["pdf", "docx", "png", "jpg", "jpeg"])
            syl_text = st.text_area("Or paste the text", height=100)
            if st.form_submit_button("Read syllabus", type="primary") and (syl_file is not None or syl_text.strip()):
                try:
                    extracted, info = parse_syllabus_multimodal(syl_file, syl_text, course_tag)
                    added_count, _ = add_rows_dedup(extracted)
                    message = f"Added {added_count} item{'s' if added_count != 1 else ''}."
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
                        message += f" Saved {info_course}'s totals ({', '.join(found)})."
                    flash(message)
                    st.rerun()
                except Exception as e:
                    st.error(f"Couldn't read that syllabus: {e}")

    with tab_one:
        with st.form("add_item_form", clear_on_submit=True):
            a1, a2 = st.columns([1, 2])
            m_course = a1.text_input("Class", value="General")
            m_title = a2.text_input("What's due")
            a3, a4 = st.columns(2)
            m_date = a3.date_input("Due date")
            m_type = a4.selectbox("Type", TYPE_OPTIONS, format_func=type_label)
            with st.expander("Hours and effort (optional, for Study coach)"):
                m_hours = st.number_input("Hours", min_value=0.25, max_value=40.0, value=1.5, step=0.25)
                m_diff = st.slider("Effort", 1, 5, 3)
            if st.form_submit_button("Add", type="primary") and m_title.strip():
                add_rows_dedup([{
                    "course": m_course.strip() or "General",
                    "date": m_date.strftime("%Y-%m-%d"),
                    "title": m_title.strip(),
                    "type": m_type,
                    "hours": m_hours,
                    "difficulty": m_diff,
                    "done": "no",
                }])
                flash(f"Added {m_title.strip()}.")
                st.rerun()

def page_settings():
    show_flash()
    page_header("Settings", "Your account.", f"Signed in as <b>{esc(user.email)}</b>")
    with st.form("settings_form"):
        updated_name = st.text_input("Name", value=display_name)
        new_cap = st.slider("Study hours a day", 2.0, 14.0, daily_capacity, 0.5, help="Only used by Study coach.")
        if st.form_submit_button("Save", type="primary"):
            try:
                save_profile_meta({"full_name": updated_name.strip() or display_name, "daily_capacity": new_cap})
                flash("Saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Couldn't save: {e}")
    st.write("")
    if st.button("Log out", icon=":material/logout:"):
        supabase.auth.sign_out()
        st.session_state["user"] = None
        st.session_state["session"] = None
        st.rerun()

# ---------- Navigation (top bar) ----------
PAGES = {
    "home": st.Page(page_home, title="Home", icon=":material/home:", url_path="home", default=True),
    "semester": st.Page(page_semester, title="Semester", icon=":material/show_chart:", url_path="semester"),
    "calendar": st.Page(page_calendar, title="Calendar", icon=":material/calendar_month:", url_path="calendar"),
    "tasks": st.Page(page_tasks, title="Tasks", icon=":material/check_circle:", url_path="tasks"),
    "classes": st.Page(page_classes, title="Classes", icon=":material/school:", url_path="classes"),
    "coach": st.Page(page_coach, title="Study coach", icon=":material/auto_awesome:", url_path="coach"),
    "add": st.Page(page_add, title="Add & sync", icon=":material/add_circle:", url_path="add"),
    "settings": st.Page(page_settings, title="Settings", icon=":material/settings:", url_path="settings"),
}
st.navigation(list(PAGES.values()), position="top").run()
