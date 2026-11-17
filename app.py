import os

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

DATA_FILE = "items.csv" if os.path.exists("items.csv") else "sample_items.csv"

st.set_page_config(page_title="Semester Planner", layout="wide")
st.title("Semester Planner")

# ---------- Add-item form (sidebar) ----------
with st.sidebar:
    st.header("Add an item")
    with st.form("add_item", clear_on_submit=True):
        new_title = st.text_input("Title")
        new_date = st.date_input("Date")
        new_type = st.selectbox("Type", ["assignment", "exam", "recurring", "job", "other"])
        new_hours = st.number_input("Estimated hours", min_value=0.25, max_value=40.0, value=1.0, step=0.25)
        new_difficulty = st.slider("Difficulty (1 easy, 5 hard)", 1, 5, 3)
        submitted = st.form_submit_button("Add")

    if submitted:
        if new_title.strip() == "":
            st.warning("Please enter a title.")
        else:
            existing = pd.read_csv(DATA_FILE)
            new_row = pd.DataFrame([{
                "date": new_date.strftime("%Y-%m-%d"),
                "title": new_title.strip(),
                "type": new_type,
                "hours": new_hours,
                "difficulty": new_difficulty,
                "done": "no",
            }])
            pd.concat([existing, new_row], ignore_index=True).to_csv(DATA_FILE, index=False)
            st.success("Added!")

# ---------- Load data and compute load ----------
df = pd.read_csv(DATA_FILE, parse_dates=["date"])
df["effort"] = df["hours"] * (0.5 + df["difficulty"] * 0.25)

SPREAD_DAYS = {"exam": 7, "assignment": 4}

rows = []
for _, r in df.iterrows():
    n = SPREAD_DAYS.get(r["type"], 1)
    days = pd.date_range(end=r["date"], periods=n)
    weights = np.arange(1, n + 1)
    weights = weights / weights.sum()
    for d, w in zip(days, weights):
        rows.append({"date": d, "effort": r["effort"] * w})

spread = pd.DataFrame(rows)
daily = spread.groupby("date")["effort"].sum().asfreq("D", fill_value=0).reset_index()

low = daily["effort"].quantile(1 / 3)
high = daily["effort"].quantile(2 / 3)

def level(x):
    if x <= low:
        return "Low"
    elif x <= high:
        return "Medium"
    return "High"

daily["level"] = daily["effort"].apply(level)
threshold = daily["effort"].mean() + daily["effort"].std()
daily["peak"] = daily["effort"] > threshold

# ---------- Morning brief ----------
today = pd.Timestamp.today().normalize()
st.header("Morning brief")

col1, col2, col3 = st.columns(3)

week = daily[(daily["date"] >= today) & (daily["date"] < today + pd.Timedelta(days=7))]
col1.metric("Load this week", round(week["effort"].sum(), 1))

upcoming_peaks = daily[(daily["date"] >= today) & daily["peak"]]
if upcoming_peaks.empty:
    col2.metric("Next peak day", "None coming up")
else:
    col2.metric("Next peak day", upcoming_peaks.iloc[0]["date"].strftime("%b %d"))

todays = daily[daily["date"] == today]
col3.metric("Today's level", todays.iloc[0]["level"] if not todays.empty else "No data")

st.subheader("Today (tick the box when something is done)")
today_items = df[df["date"] == today].copy()
if today_items.empty:
    st.write("Nothing scheduled today.")
else:
    today_items["done"] = today_items["done"] == "yes"
    edited = st.data_editor(
        today_items[["title", "type", "hours", "difficulty", "done"]],
        disabled=["title", "type", "hours", "difficulty"],
        hide_index=True,
    )
    changed = edited["done"] != today_items["done"]
    if changed.any():
        full = pd.read_csv(DATA_FILE)
        for idx in edited.index[changed]:
            full.loc[idx, "done"] = "yes" if edited.loc[idx, "done"] else "no"
        full.to_csv(DATA_FILE, index=False)
        st.rerun()

st.subheader("Needs attention (next 3 days, not done, difficulty 4+)")
soon = df[
    (df["date"] >= today)
    & (df["date"] <= today + pd.Timedelta(days=3))
    & (df["done"] == "no")
    & (df["difficulty"] >= 4)
    & (df["type"] != "recurring")
].copy()
soon["date"] = soon["date"].dt.strftime("%b %d")
if soon.empty:
    st.write("Nothing urgent.")
else:
    st.dataframe(soon[["date", "title", "type", "hours", "difficulty"]])

st.subheader("Resolved (finished in the last 7 days)")
resolved = df[
    (df["done"] == "yes")
    & (df["date"] >= today - pd.Timedelta(days=7))
    & (df["date"] <= today)
    & (df["type"] != "recurring")
].copy()
if resolved.empty:
    st.write("Nothing marked done yet.")
else:
    resolved["date"] = resolved["date"].dt.strftime("%b %d")
    st.dataframe(resolved[["date", "title", "type", "hours", "difficulty"]], hide_index=True)

# ---------- Semester graph ----------
st.header("Semester load")

fig = px.line(daily, x="date", y="effort")
dots = px.scatter(
    daily, x="date", y="effort", color="level",
    color_discrete_map={"Low": "green", "Medium": "gold", "High": "red"},
)
for trace in dots.data:
    fig.add_trace(trace)

peaks = daily[daily["peak"]]
fig.add_scatter(
    x=peaks["date"], y=peaks["effort"], mode="markers",
    marker=dict(symbol="star", size=16, color="black"), name="Peak",
)
fig.update_xaxes(rangeslider_visible=True)

st.plotly_chart(fig)

import os
import json
from datetime import datetime, timedelta
import pandas as pd
import requests
import icalendar
import recurring_ical_events
from pypdf import PdfReader
from google import genai
import streamlit as st

st.set_page_config(page_title="Semester Planner", layout="wide")

DATA_FILE = "items.csv" if os.path.exists("items.csv") else "sample_items.csv"

# 1. Isolate each visitor's schedule in session_state
if "df" not in st.session_state:
    st.session_state["df"] = pd.read_csv(DATA_FILE, parse_dates=["date"])

# Helper to append new rows safely
def add_rows(new_rows: list[dict]):
    if not new_rows:
        return
    new_df = pd.DataFrame(new_rows)
    new_df["date"] = pd.to_datetime(new_df["date"])
    st.session_state["df"] = pd.concat([st.session_state["df"], new_df], ignore_index=True)

# 2. Import Google Calendar or Canvas .ics URL
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

        if hasattr(dtstart, "hour"):
            duration_hrs = round(max((dtend - dtstart).total_seconds() / 3600, 0.5), 2)
            date_str = dtstart.strftime("%Y-%m-%d")
        else:
            duration_hrs = 2.0
            date_str = dtstart.strftime("%Y-%m-%d")

        lower = title.lower()
        if any(w in lower for w in ["exam", "midterm", "final", "test", "quiz"]):
            item_type, diff = "exam", 5
        elif any(w in lower for w in ["homework", "hw", "project", "lab", "assignment", "paper"]):
            item_type, diff = "assignment", 3
        else:
            item_type, diff = "recurring", 2

        rows.append({
            "date": date_str,
            "title": title,
            "type": item_type,
            "hours": duration_hrs,
            "difficulty": diff,
            "done": "no",
        })
    return rows

# 3. Parse PDF Syllabus using Gemini API
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
    - "hours": estimated study/work hours (number, e.g. 2, 4, 8)
    - "difficulty": integer from 1 to 5
    - "done": "no"

    Syllabus text:
    {full_text[:15000]}
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    raw = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)

# ---------- Sidebar Controls ----------
with st.sidebar:
    st.header("1. Import Schedule")

    with st.expander("Connect Google Calendar / Canvas (.ics)", expanded=False):
        ics_link = st.text_input("Paste secret .ics URL", placeholder="[https://calendar.google.com/calendar/ical/](https://calendar.google.com/calendar/ical/)...")
        if st.button("Import Calendar Events") and ics_link:
            try:
                imported = parse_ics_url(ics_link)
                add_rows(imported)
                st.success(f"Imported {len(imported)} events!")
            except Exception as e:
                st.error(f"Could not read calendar link: {e}")

    with st.expander("Upload Syllabus (PDF)", expanded=False):
        pdf_file = st.file_uploader("Upload course syllabus", type=["pdf"])
        if st.button("Extract Syllabus Deadlines") and pdf_file:
            try:
                extracted = parse_syllabus_pdf(pdf_file)
                add_rows(extracted)
                st.success(f"Added {len(extracted)} syllabus items!")
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
            st.success("Added!")

    st.divider()
    st.header("3. Save / Load Your Data")
    csv_bytes = st.session_state["df"].to_csv(index=False).encode("utf-8")
    st.download_button("Download My Schedule (.csv)", data=csv_bytes, file_name="my_semester.csv", mime="text/csv")

    uploaded_csv = st.file_uploader("Load Saved Schedule (.csv)", type=["csv"])
    if uploaded_csv is not None:
        st.session_state["df"] = pd.read_csv(uploaded_csv, parse_dates=["date"])
        st.success("Loaded your schedule!")

    if st.button("Clear All & Start Fresh"):
        st.session_state["df"] = st.session_state["df"].iloc[0:0]
        st.rerun()

# ---------- Load data and compute load ----------
df = st.session_state["df"].copy()
df["effort"] = df["hours"] * (0.5 + df["difficulty"] * 0.25)