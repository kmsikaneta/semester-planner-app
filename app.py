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