import json
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import icalendar
import recurring_ical_events
from pypdf import PdfReader
from google import genai
from supabase import create_client
import streamlit as st

st.set_page_config(page_title="Semester Planner", layout="wide")

# Initialize Supabase client
supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# ---------- Authentication Gate ----------
if "user" not in st.session_state:
    st.session_state["user"] = None

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
                    st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")

    with tab_signup:
        with st.form("signup_form"):
            new_email = st.text_input("Email")
            new_password = st.text_input("Password (min 6 characters)", type="password")
            if st.form_submit_button("Create Account"):
                try:
                    res = supabase.auth.sign_up({"email": new_email, "password": new_password})
                    if res.user:
                        st.session_state["user"] = res.user
                        st.success("Account created!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Sign up failed: {e}")

    st.stop()

# ---------- Logged-In User Helpers ----------
user_id = st.session_state["user"].id

def load_user_df() -> pd.DataFrame:
    res = supabase.table("items").select("*").eq("user_id", user_id).execute()
    if not res.data:
        return pd.DataFrame(columns=["id", "date", "title", "type", "hours", "difficulty", "done"])
    df = pd.DataFrame(res.data)
    df["date"] = pd.to_datetime(df["date"])
    df["hours"] = df["hours"].astype(float)
    df["difficulty"] = df["difficulty"].astype(int)
    return df

def add_rows(new_rows: list[dict]):
    if not new_rows:
        return
    for row in new_rows:
        row["user_id"] = user_id
    supabase.table("items").insert(new_rows).execute()

def toggle_done(item_id: int, current_status: str):
    new_status = "yes" if current_status == "no" else "no"
    supabase.table("items").update({"done": new_status}).eq("id", item_id).execute()

def delete_item(item_id: int):
    supabase.table("items").delete().eq("id", item_id).execute()

def parse_ics_url(ics_url: str) -> list[dict]:
    resp = requests.get(ics_url.strip(), timeout=15)
    resp.raise_for_status()
    cal = icalendar.Calendar.from_ical(resp.content)

    start_window = datetime.now() - timedelta(days=7)
    end_window = datetime.now() + timedelta(days=120)
    events = recurring_ical_events.of(cal).between(start_window, end_window)

    rows = []
    for event in events:
        title = str(event.get("SUMMARY", "Calendar Event")).replace(",", " ")
        dtstart = event.get("DTSTART").dt
        dtend = event.get("DTEND").dt if event.get("DTEND") else dtstart
        duration_hrs = round(max((dtend - dtstart).total_seconds() / 3600, 0.5), 2) if hasattr(dtstart, "hour") else 2.0

        lower = title.lower()
        if any(w in lower for w in ["exam", "midterm", "final", "test", "quiz"]):
            item_type, diff = "exam", 5
        elif any(w in lower for w in ["homework", "hw", "project", "lab", "assignment", "paper"]):
            item_type, diff = "assignment", 3
        else:
            item_type, diff = "recurring", 2

        rows.append({
            "date": dtstart.strftime("%Y-%m-%d"),
            "title": title,
            "type": item_type,
            "hours": duration_hrs,
            "difficulty": diff,
            "done": "no",
        })
    return rows

def parse_syllabus_pdf(uploaded_file) -> list[dict]:
    reader = PdfReader(uploaded_file)
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    prompt = f"""
    Extract all graded assignments, quizzes, projects, and exams with due dates from this syllabus.
    Return ONLY a valid JSON array of objects with these exact keys:
    - "date": "YYYY-MM-DD" (use 2026 if year is omitted)
    - "title": string without commas
    - "type": "exam" or "assignment"
    - "hours": estimated study/work hours (number)
    - "difficulty": integer from 1 to 5
    - "done": "no"

    Syllabus text:
    {full_text[:15000]}
    """
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    raw = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)

# ---------- Sidebar Controls ----------
with st.sidebar:
    st.caption(f"Signed in as **{st.session_state['user'].email}**")
    if st.button("Log Out"):
        supabase.auth.sign_out()
        st.session_state["user"] = None
        st.rerun()

    st.divider()
    st.header("1. Import Schedule")

    with st.expander("Connect Google Calendar / Canvas (.ics)"):
        ics_link = st.text_input("Paste secret .ics URL", placeholder="[https://calendar.google.com/calendar/ical/](https://calendar.google.com/calendar/ical/)...")
        if st.button("Import Calendar Events") and ics_link:
            try:
                imported = parse_ics_url(ics_link)
                add_rows(imported)
                st.success(f"Saved {len(imported)} events!")
                st.rerun()
            except Exception as e:
                st.error(f"Could not read calendar link: {e}")

    with st.expander("Upload Syllabus (PDF)"):
        pdf_file = st.file_uploader("Upload course syllabus", type=["pdf"])
        if st.button("Extract Syllabus Deadlines") and pdf_file:
            try:
                extracted = parse_syllabus_pdf(pdf_file)
                add_rows(extracted)
                st.success(f"Saved {len(extracted)} syllabus items!")
                st.rerun()
            except Exception as e:
                st.error(f"Syllabus parsing failed: {e}")

    st.divider()
    st.header("2. Add Item Manually")
    with st.form("add_item_form", clear_on_submit=True):
        title = st.text_input("Title")
        date = st.date_input("Date")
        item_type = st.selectbox("Type", ["assignment", "exam", "quiz", "reading", "recurring", "job"])
        hours = st.number_input("Estimated hours", min_value=0.25, max_value=40.0, value=1.0, step=0.25)
        difficulty = st.slider("Difficulty (1 easy, 5 hard)", 1, 5, 3)
        if st.form_submit_button("Add") and title.strip():
            add_rows([{
                "date": date.strftime("%Y-%m-%d"),
                "title": title.strip().replace(",", " "),
                "type": item_type,
                "hours": hours,
                "difficulty": difficulty,
                "done": "no",
            }])
            st.rerun()

# ---------- Load User Data & Compute Workload ----------
st.title("Semester Planner")
df = load_user_df()

if df.empty:
    st.info("Your schedule is empty! Use the sidebar to import your Canvas/Google Calendar, upload a PDF syllabus, or add an item manually.")
    st.stop()

df["effort"] = df["hours"] * (0.5 + df["difficulty"] * 0.25)

SPREAD_DAYS = {"exam": 7, "assignment": 4}
daily_records = []

for _, row in df.iterrows():
    spread = SPREAD_DAYS.get(row["type"], 1)
    weights = np.arange(1, spread + 1, dtype=float)
    weights /= weights.sum()

    for offset, w in enumerate(reversed(weights)):
        day = row["date"] - pd.Timedelta(days=offset)
        daily_records.append({
            "date": day.normalize(),
            "load": row["effort"] * w,
        })

load_df = pd.DataFrame(daily_records).groupby("date", as_index=False)["load"].sum()
full_range = pd.date_range(load_df["date"].min(), load_df["date"].max(), freq="D")
load_df = load_df.set_index("date").reindex(full_range, fill_value=0.0).rename_axis("date").reset_index()

mean_load = load_df["load"].mean()
std_load = load_df["load"].std()
peak_threshold = mean_load + std_load

q33, q66 = np.percentile(load_df["load"], [33, 66])
def load_color(val):
    if val >= q66 and val > 0:
        return "#ef4444"  # Red (high load)
    elif val >= q33 and val > 0:
        return "#eab308"  # Yellow (medium load)
    return "#22c55e"      # Green (light load)

load_df["color"] = load_df["load"].apply(load_color)

# ---------- Workload Line Graph with Zoom ----------
st.subheader("Semester Workload Forecast")
fig = go.Figure()

fig.add_trace(go.Scatter(
    x=load_df["date"],
    y=load_df["load"],
    mode="lines+markers",
    name="Daily Load",
    line=dict(color="#6366f1", width=2.5),
    marker=dict(color=load_df["color"], size=8),
))

fig.add_hline(
    y=peak_threshold,
    line_dash="dash",
    line_color="#ef4444",
    annotation_text="Peak Threshold (+1 SD)",
    annotation_position="top left",
)

fig.update_layout(
    xaxis=dict(
        rangeselector=dict(
            buttons=[
                dict(count=7, label="1w", step="day", stepmode="backward"),
                dict(count=1, label="1m", step="month", stepmode="backward"),
                dict(step="all", label="Semester"),
            ]
        ),
        rangeslider=dict(visible=True),
        type="date",
    ),
    yaxis_title="Weighted Effort Score",
    height=380,
    margin=dict(l=20, r=20, t=30, b=20),
)
st.plotly_chart(fig, use_container_width=True)

# ---------- Daily Morning Brief ----------
st.subheader("Daily Morning Brief")
today = pd.Timestamp.now().normalize()

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("#### Needs Attention (High Difficulty / Due Soon)")
    urgent = df[(df["done"] == "no") & (df["date"] >= today) & (df["date"] <= today + pd.Timedelta(days=7)) & (df["difficulty"] >= 4)]
    if urgent.empty:
        st.caption("No high-difficulty deadlines in the next 7 days.")
    else:
        for _, r in urgent.sort_values("date").iterrows():
            st.warning(f"**{r['title']}** ({r['type']}) — Due {r['date'].strftime('%b %d')} • Difficulty {r['difficulty']}/5")

with col2:
    st.markdown("#### Today & This Week")
    this_week = df[(df["date"] >= today) & (df["date"] <= today + pd.Timedelta(days=7))].sort_values("date")
    if this_week.empty:
        st.caption("Nothing scheduled for the next 7 days.")
    else:
        for _, r in this_week.iterrows():
            badge = "🔴" if r["difficulty"] >= 4 else ("🟡" if r["difficulty"] == 3 else "🟢")
            status = "~~" if r["done"] == "yes" else ""
            st.write(f"{badge} {status}**{r['title']}** ({r['date'].strftime('%a %b %d')}) — {r['hours']}h{status}")

with col3:
    st.markdown("#### Resolved / Completed")
    completed = df[df["done"] == "yes"].sort_values("date", ascending=False)
    if completed.empty:
        st.caption("No items marked done yet.")
    else:
        for _, r in completed.iterrows():
            st.success(f"✓ {r['title']} ({r['date'].strftime('%b %d')})")

# ---------- Manage & Check Off Items ----------
st.divider()
st.subheader("All Scheduled Items")

for _, row in df.sort_values("date").iterrows():
    c1, c2, c3, c4, c5 = st.columns([0.5, 3, 1.5, 1.5, 0.7])
    is_done = row["done"] == "yes"
    if c1.checkbox("", value=is_done, key=f"chk_{row['id']}") != is_done:
        toggle_done(int(row["id"]), row["done"])
        st.rerun()
    c2.write(f"**{row['title']}** ({row['type']})")
    c3.write(row["date"].strftime("%Y-%m-%d"))
    c4.write(f"{row['hours']}h • Diff {row['difficulty']}/5")
    if c5.button("🗑️", key=f"del_{row['id']}"):
        delete_item(int(row["id"]))
        st.rerun()