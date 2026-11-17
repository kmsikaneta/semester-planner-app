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
from supabase import create_client
from streamlit_calendar import calendar
import streamlit as st

st.set_page_config(page_title="Semester Planner", layout="wide")

MODEL_ID = "gemini-3.8-flash"

# Initialize Supabase client
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

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
            full_name = st.text_input("Your First Name (e.g., Maya)")
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

# ---------- User Profile, Preferences & Time-of-Day Greeting ----------
user = st.session_state["user"]
user_id = user.id
meta = user.user_metadata or {}
display_name = meta.get("full_name") or user.email.split("@")[0].capitalize()

# Load saved user calibration settings (stored cleanly in Supabase user_metadata)
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

# ---------- Database & AI Parsing Helpers ----------
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

def detect_course_code(summary: str) -> str:
    match = re.search(r"\b([A-Z]{2,4}[\s-]?\d{3,4}[A-Z]?)\b", summary.upper())
    return match.group(1).replace("-", " ") if match else "General"

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
        dtstart = event.get("DTSTART").dt
        dtend = event.get("DTEND").dt if event.get("DTEND") else dtstart
        duration_hrs = round(max((dtend - dtstart).total_seconds() / 3600, 0.5), 2) if hasattr(dtstart, "hour") else 2.0

        course = detect_course_code(raw_summary)
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
            "title": raw_summary,
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
    res = client.models.generate_content(model=MODEL_ID, contents=prompt)
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

    response = client.models.generate_content(model=MODEL_ID, contents=contents)
    raw = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)

def generate_study_plan(df: pd.DataFrame, load_df: pd.DataFrame) -> str:
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    today = pd.Timestamp.now().normalize()
    upcoming_items = df[(df["done"] == "no") & (df["date"] >= today) & (df["date"] <= today + pd.Timedelta(days=14))]
    peak_days = load_df[(load_df["date"] >= today) & (load_df["date"] <= today + pd.Timedelta(days=14)) & (load_df["intensity"] >= 6.0)]

    items_summary = upcoming_items[["course", "date", "title", "type", "hours", "difficulty"]].to_dict(orient="records")
    peaks_summary = peak_days[["date", "intensity"]].to_dict(orient="records")

    prompt = f"""
    You are an academic coach for {display_name}. Today is {today.strftime('%Y-%m-%d')}.
    Their target daily study capacity is {daily_capacity} hours/day.
    Upcoming peak workload days (0-10 scale): {peaks_summary}
    Upcoming unfinished tasks for the next 14 days: {items_summary}

    Create a concise, actionable day-by-day study plan for the next 7 days to flatten their peak crunch days.
    Group recommendations by day, name exact courses and assignments, and suggest realistic hour blocks within their {daily_capacity}h/day limit.
    """
    res = client.models.generate_content(model=MODEL_ID, contents=prompt)
    return res.text

# ---------- Sidebar Controls ----------
with st.sidebar:
    st.caption(f"Signed in as **{display_name}** ({user.email})")

    with st.expander("Profile & Capacity Calibration"):
        updated_name = st.text_input("Display Name", value=display_name)
        new_cap = st.slider("Max Daily Study Capacity (hrs)", 2.0, 14.0, daily_capacity, 0.5,
                            help="Lower this if you work a part-time job or have heavy extracurriculars.")
        new_exam_sp = st.slider("Exam Prep Spread (days before due)", 2, 14, exam_spread)
        new_assign_sp = st.slider("Assignment Prep Spread (days before due)", 1, 10, assign_spread)
        if st.button("Save Preferences"):
            res = supabase.auth.update_user({
                "data": {
                    "full_name": updated_name.strip() or display_name,
                    "daily_capacity": new_cap,
                    "exam_spread": new_exam_sp,
                    "assign_spread": new_assign_sp,
                }
            })
            st.session_state["user"] = res.user
            st.success("Preferences saved!")
            st.rerun()

    if st.button("Log Out"):
        supabase.auth.sign_out()
        st.session_state["user"] = None
        st.session_state["session"] = None
        st.rerun()

    st.divider()
    st.header("1. Import Schedule")

    with st.expander("Sync Google Calendar / Canvas (.ics)"):
        ics_link = st.text_input("Paste secret .ics URL", placeholder="https://...")
        if st.button("Sync Calendar (Auto-Deduplicates)") and ics_link:
            try:
                imported = parse_ics_url(ics_link)
                added_count = add_rows_dedup(imported)
                st.success(f"Added {added_count} new events ({len(imported) - added_count} duplicates skipped).")
                st.rerun()
            except Exception as e:
                st.error(f"Calendar sync failed: {e}")

    with st.expander("AI Syllabus / Schedule Extractor"):
        course_tag = st.text_input("Course Tag (optional)", placeholder="e.g., ITSC 3155")
        syl_file = st.file_uploader("Upload PDF, Word (.docx), or Schedule Screenshot", type=["pdf", "docx", "png", "jpg", "jpeg"])
        syl_text = st.text_area("Or paste syllabus / Canvas schedule text", height=90)
        if st.button("Extract Deadlines") and (syl_file is not None or syl_text.strip()):
            try:
                extracted = parse_syllabus_multimodal(syl_file, syl_text, course_tag)
                added_count = add_rows_dedup(extracted)
                st.success(f"Added {added_count} new items!")
                st.rerun()
            except Exception as e:
                st.error(f"Extraction failed: {e}")

    st.divider()
    st.header("2. Add Item Manually")
    with st.form("add_item_form", clear_on_submit=True):
        m_course = st.text_input("Course", value="General")
        m_title = st.text_input("Title")
        m_date = st.date_input("Date")
        m_type = st.selectbox("Type", ["assignment", "exam", "quiz", "reading", "recurring", "job"])
        m_hours = st.number_input("Estimated hours", min_value=0.25, max_value=40.0, value=1.5, step=0.25)
        m_diff = st.slider("Difficulty (1 easy, 5 hard)", 1, 5, 3)
        if st.form_submit_button("Add") and m_title.strip():
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

# ---------- Main Header, Today Summary & Quick-Add Bar ----------
df = load_user_df()
today_local = pd.Timestamp(datetime.now(ZoneInfo("America/New_York")).date())

st.title(get_greeting(display_name))

# 1-2 sentence dynamic summary of what's due today
if not df.empty:
    due_today = df[(df["done"] == "no") & (df["date"].dt.normalize() == today_local)]
    if due_today.empty:
        next_up = df[(df["done"] == "no") & (df["date"].dt.normalize() > today_local)].sort_values("date")
        if next_up.empty:
            st.markdown("##### You have nothing due today and no upcoming deadlines on your schedule.")
        else:
            nxt = next_up.iloc[0]
            st.markdown(f"##### You have nothing due today. Next up: **{nxt['title']}** ({nxt['course']}) on {nxt['date'].strftime('%b %d')}.")
    elif len(due_today) == 1:
        item = due_today.iloc[0]
        st.markdown(f"##### You have **{item['title']}** ({item['course']}) due today ({item['hours']}h estimated).")
    else:
        prioritized = due_today.sort_values(["difficulty", "hours"], ascending=False)
        top_item = prioritized.iloc[0]["title"]
        others = len(due_today) - 1
        noun = "item" if others == 1 else "items"
        st.markdown(f"##### You have **{top_item}** and {others} other {noun} due today.")

st.caption("**AI Quick-Add:** Type any assignment, exam, or shift in plain English below to automatically schedule it.")
with st.form("quick_nl_form", clear_on_submit=True):
    q_col1, q_col2 = st.columns([4, 1.3])
    nl_prompt = q_col1.text_input(
        "Quick Add (AI)",
        placeholder="e.g., 'ITSC 3155 Midterm next Thursday takes 6 hours diff 5'",
        label_visibility="collapsed",
    )
    if q_col2.form_submit_button("✨ Quick Add", use_container_width=True) and nl_prompt.strip():
        try:
            parsed_items = parse_quick_natural_language(nl_prompt.strip())
            added = add_rows_dedup(parsed_items)
            st.success(f"Added {added} item(s)!")
            st.rerun()
        except Exception as e:
            st.error(f"Could not parse quick add: {e}")

if df.empty:
    st.info("Your schedule is empty! Use the Quick-Add bar above or the sidebar to sync Canvas/Google Calendar or upload a syllabus.")
    st.stop()
if df.empty:
    st.info("Your schedule is empty! Use the Quick Add bar above or the sidebar to sync Canvas/Google Calendar or upload a syllabus.")
    st.stop()

# Course Filter Bar
all_courses = sorted(df["course"].unique().tolist())
selected_courses = st.multiselect("Filter by Course", options=all_courses, default=all_courses)
filtered_df = df[df["course"].isin(selected_courses)].copy()

if filtered_df.empty:
    st.warning("No items match your selected course filters.")
    st.stop()

# ---------- Compute Calibrated Time-Spread Workload & 0-10 Intensity ----------
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

# Scale 0-10 dynamically against the user's personal daily study capacity
max_reference_effort = daily_capacity * 1.5
load_df["intensity"] = (load_df["load"] / max_reference_effort * 10).clip(0, 10).round(1)
peak_threshold = min(round(load_df["intensity"].mean() + load_df["intensity"].std(), 1), 9.5)

def load_color(val):
    if val >= 6.5:
        return "#ef4444"
    elif val >= 3.0:
        return "#eab308"
    return "#22c55e"

load_df["color"] = load_df["intensity"].apply(load_color)

# ---------- Navigation Tabs ----------
tab_overview, tab_cal, tab_table, tab_coach = st.tabs([
    "📊 Workload Overview",
    "📅 Calendar Grid",
    "📝 Master Task Editor",
    "🧠 AI Study Coach",
])

with tab_overview:
    col_hdr, col_toggle = st.columns([3, 1])
    with col_hdr:
        st.subheader("Semester Workload Forecast")
    with col_toggle:
        chart_mode = st.radio("Chart View", ["Total Intensity Line", "Stacked by Course"], horizontal=True)

    with st.expander(f"How to read your Workload Intensity Score (Calibrated to {daily_capacity}h/day capacity)", expanded=False):
        st.markdown("""
        * **0 – 2.9 (🟢 Light / Free):** Nothing due or light routine tasks; great time to get ahead or rest.
        * **3.0 – 6.4 (🟡 Moderate):** Steady classes, readings, or early assignment prep.
        * **6.5 – 10.0 (🔴 Heavy / Crunch):** High volume of hours and/or high-difficulty exams and deadlines stacked together.
        """)

    if chart_mode == "Total Intensity Line":
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=load_df["date"],
            y=load_df["intensity"],
            mode="lines+markers",
            name="Workload Intensity",
            line=dict(color="#6366f1", width=3, shape="spline", smoothing=0.4),
            fill="tozeroy",
            fillcolor="rgba(99, 102, 241, 0.10)",
            marker=dict(color=load_df["color"], size=8, line=dict(width=1, color="white")),
            hovertemplate="<b>%{x|%b %d, %Y}</b><br>Workload Intensity: <b>%{y}/10</b><extra></extra>",
        ))
        fig.add_hline(
            y=peak_threshold,
            line_dash="dash",
            line_color="#ef4444",
            annotation_text=f"Your Peak Threshold ({peak_threshold}/10)",
            annotation_position="top left",
        )
        fig.update_layout(
            xaxis=dict(
                rangeselector=dict(buttons=[
                    dict(count=7, label="1w", step="day", stepmode="backward"),
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(step="all", label="Semester"),
                ]),
                rangeslider=dict(visible=True),
                type="date",
            ),
            yaxis=dict(
                title="Workload Intensity (0–10)",
                range=[-0.4, 10.6],
                tickmode="array",
                tickvals=[0, 2.5, 5, 7.5, 10],
                ticktext=["0 (Free)", "2.5", "5 (Moderate)", "7.5", "10 (Max Load)"],
            ),
            height=400,
            margin=dict(l=20, r=20, t=30, b=20),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        course_daily = raw_daily.groupby(["date", "course"], as_index=False)["load"].sum()
        course_daily["intensity"] = (course_daily["load"] / max_reference_effort * 10).clip(0, 10).round(2)
        fig_stack = px.area(
            course_daily,
            x="date",
            y="intensity",
            color="course",
            labels={"intensity": "Workload Intensity (0–10)", "date": "Date", "course": "Course"},
        )
        fig_stack.update_layout(
            xaxis=dict(rangeslider=dict(visible=True), type="date"),
            yaxis=dict(range=[0, 10.6]),
            height=400,
            margin=dict(l=20, r=20, t=30, b=20),
            hovermode="x unified",
        )
        st.plotly_chart(fig_stack, use_container_width=True)

    # ---------- Daily Brief ----------
    st.subheader("Daily Brief")
    today = pd.Timestamp.now().normalize()
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("#### Needs Attention")
        urgent = filtered_df[
            (filtered_df["done"] == "no")
            & (filtered_df["date"] >= today)
            & (filtered_df["date"] <= today + pd.Timedelta(days=7))
            & (filtered_df["difficulty"] >= 4)
        ]
        if urgent.empty:
            st.caption("No high-difficulty deadlines in the next 7 days.")
        else:
            for _, r in urgent.sort_values("date").iterrows():
                st.warning(f"**[{r['course']}] {r['title']}** — Due {r['date'].strftime('%b %d')} • Diff {r['difficulty']}/5")

    with c2:
        st.markdown("#### Today & This Week")
        this_week = filtered_df[
            (filtered_df["date"] >= today) & (filtered_df["date"] <= today + pd.Timedelta(days=7))
        ].sort_values("date")
        if this_week.empty:
            st.caption("Nothing scheduled for the next 7 days.")
        else:
            for _, r in this_week.iterrows():
                badge = "🔴" if r["difficulty"] >= 4 else ("🟡" if r["difficulty"] == 3 else "🟢")
                strike = "~~" if r["done"] == "yes" else ""
                st.write(f"{badge} {strike}**[{r['course']}] {r['title']}** ({r['date'].strftime('%a %b %d')}) — {r['hours']}h{strike}")

    with c3:
        st.markdown("#### Resolved / Completed")
        completed = filtered_df[filtered_df["done"] == "yes"].sort_values("date", ascending=False)
        if completed.empty:
            st.caption("No items marked done yet.")
        else:
            for _, r in completed.iterrows():
                st.success(f"✓ [{r['course']}] {r['title']} ({r['date'].strftime('%b %d')})")

with tab_cal:
    st.subheader("Interactive Semester Calendar")
    st.caption("Color-coded by difficulty: 🔴 High (4–5) • 🟡 Medium (3) • 🟢 Low (1–2) • ⚪ Completed")

    cal_events = []
    for _, r in filtered_df.iterrows():
        if r["done"] == "yes":
            bg = "#9ca3af"
        elif r["difficulty"] >= 4:
            bg = "#ef4444"
        elif r["difficulty"] == 3:
            bg = "#eab308"
        else:
            bg = "#22c55e"

        cal_events.append({
            "title": f"[{r['course']}] {r['title']} ({r['hours']}h)",
            "start": r["date"].strftime("%Y-%m-%d"),
            "end": r["date"].strftime("%Y-%m-%d"),
            "backgroundColor": bg,
            "borderColor": bg,
        })

    calendar(
        events=cal_events,
        options={
            "initialView": "dayGridMonth",
            "headerToolbar": {
                "left": "prev,next today",
                "center": "title",
                "right": "dayGridMonth,listWeek",
            },
            "height": 620,
        },
        key="semester_calendar_grid",
    )

with tab_table:
    st.subheader("Edit, Re-tag, or Delete Schedule Items")
    st.caption("Double-click any cell to edit course tags, dates, hours, or difficulty, check off completed work, or select rows to delete.")

    edit_df = filtered_df[["id", "done", "course", "date", "title", "type", "hours", "difficulty"]].sort_values("date").copy()
    edit_df["done"] = edit_df["done"] == "yes"
    edit_df["date"] = edit_df["date"].dt.date
    edit_df["Delete"] = False

    edited = st.data_editor(
        edit_df,
        hide_index=True,
        use_container_width=True,
        disabled=["id"],
        column_config={
            "id": None,
            "done": st.column_config.CheckboxColumn("Done", width="small"),
            "course": st.column_config.TextColumn("Course", width="small"),
            "date": st.column_config.DateColumn("Due Date", width="small"),
            "title": st.column_config.TextColumn("Title", width="large"),
            "type": st.column_config.SelectboxColumn("Type", options=["assignment", "exam", "quiz", "reading", "recurring", "job"], width="small"),
            "hours": st.column_config.NumberColumn("Hours", min_value=0.25, max_value=40.0, step=0.25, width="small"),
            "difficulty": st.column_config.NumberColumn("Diff (1-5)", min_value=1, max_value=5, step=1, width="small"),
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
                row["done"] != orig.get("done")
                or row["course"] != orig.get("course")
                or str(row["date"]) != str(orig.get("date"))
                or row["title"] != orig.get("title")
                or row["type"] != orig.get("type")
                or float(row["hours"]) != float(orig.get("hours"))
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
        st.success("All changes saved to your database!")
        st.rerun()

with tab_coach:
    st.subheader("AI Crunch-Week Study Plan Generator")
    st.write(f"Analyze your upcoming red/yellow workload spikes against your **{daily_capacity}h/day** study capacity and generate a day-by-day schedule.")
    if st.button("Generate My 7-Day Study Plan", type="primary"):
        with st.spinner("Analyzing your upcoming deadlines and workload peaks..."):
            try:
                plan_md = generate_study_plan(filtered_df, load_df)
                st.markdown(plan_md)
            except Exception as e:
                st.error(f"Could not generate study plan: {e}")