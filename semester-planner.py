import numpy as np
import pandas as pd
import plotly.express as px

df = pd.read_csv("items.csv", parse_dates=["date"])

# Effort = hours scaled by difficulty
df["effort"] = df["hours"] * (0.5 + df["difficulty"] * 0.25)

# How many days before the due date the work is spread over
SPREAD_DAYS = {"exam": 7, "assignment": 4}

rows = []
for _, r in df.iterrows():
    n = SPREAD_DAYS.get(r["type"], 1)  # other types stay on their own day
    days = pd.date_range(end=r["date"], periods=n)
    weights = np.arange(1, n + 1)  # more weight closer to the deadline
    weights = weights / weights.sum()
    for d, w in zip(days, weights):
        rows.append({"date": d, "effort": r["effort"] * w})

spread = pd.DataFrame(rows)
daily = spread.groupby("date")["effort"].sum().asfreq("D", fill_value=0).reset_index()

# Color levels: bottom third = Low, middle third = Medium, top third = High
low = daily["effort"].quantile(1 / 3)
high = daily["effort"].quantile(2 / 3)

def level(x):
    if x <= low:
        return "Low"
    elif x <= high:
        return "Medium"
    return "High"

daily["level"] = daily["effort"].apply(level)

# Peak days = more than 1 standard deviation above the average
threshold = daily["effort"].mean() + daily["effort"].std()
daily["peak"] = daily["effort"] > threshold
print(daily)

# Line, then colored dots on top
fig = px.line(daily, x="date", y="effort", title="Semester load")
dots = px.scatter(
    daily, x="date", y="effort", color="level",
    color_discrete_map={"Low": "green", "Medium": "gold", "High": "red"},
)
for trace in dots.data:
    fig.add_trace(trace)

# Mark peak days with stars
peaks = daily[daily["peak"]]
fig.add_scatter(
    x=peaks["date"], y=peaks["effort"], mode="markers",
    marker=dict(symbol="star", size=16, color="black"), name="Peak",
)

fig.update_xaxes(rangeslider_visible=True)
fig.show()