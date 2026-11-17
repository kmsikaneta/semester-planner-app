"""Busyness scoring: how busy each day and week is, based on what's DUE.

Agreed Nov 16 (Sunny): the graph tracks what's due or happening on a day.
It does not spread work across the days before a deadline, and it does not
use hours or difficulty. Kaya owns this math: every number below is a
starting point to tune on both of our real semesters.

Rules
- Each item counts on its due date only.
- Weight by type: exam 4, quiz 3, assignment 2, reading 1, job/social 1.
- Class meetings ("recurring") count 0.
- Batch rule: many small items from one class on one day count as one heavy
  day. The first non-exam item counts in full, each extra adds +0.5, and the
  extras are capped at +4. Exams always count in full.
- Done items still count. The graph shows how busy a day IS, not how much is
  left, so checking things off never makes the past look emptier.
"""

from __future__ import annotations

import pandas as pd

TYPE_WEIGHTS = {
    "exam": 4.0,
    "quiz": 3.0,
    "assignment": 2.0,
    "reading": 1.0,
    "job": 1.0,
    "social": 1.0,
    "recurring": 0.0,
}
DEFAULT_WEIGHT = 2.0          # unknown types count like an assignment
BATCH_EXTRA = 0.5
BATCH_CAP = 4.0

LEVELS = ["open", "calm", "steady", "busy", "peak"]

# Lower bound of each level (open is exactly 0).
DAILY_THRESHOLDS = {"calm": 0.01, "steady": 4.0, "busy": 7.0, "peak": 10.0}
WEEKLY_THRESHOLDS = {"calm": 0.01, "steady": 10.0, "busy": 15.0, "peak": 21.0}

# Matches tokens.css (--busy-*).
LEVEL_FILL = {
    "open": "#ecebe8",
    "calm": "#aee8bc",
    "steady": "#ebcb67",
    "busy": "#f09a53",
    "peak": "#e06049",
}
LEVEL_INK = {
    "open": "#686D7A",
    "calm": "#2b633d",
    "steady": "#685300",
    "busy": "#804300",
    "peak": "#8b3627",
}


def level_for(score: float, thresholds: dict[str, float]) -> str:
    level = "open"
    for name in ["calm", "steady", "busy", "peak"]:
        if score >= thresholds[name]:
            level = name
    return level


def _score_group(types: list[str]) -> float:
    """Score one class's items on one day, with the batch rule."""
    score = 0.0
    others = []
    for t in types:
        w = TYPE_WEIGHTS.get(t, DEFAULT_WEIGHT)
        if t == "exam":
            score += w
        elif w > 0:
            others.append(w)
    if others:
        others.sort(reverse=True)
        score += others[0] + min(BATCH_EXTRA * (len(others) - 1), BATCH_CAP)
    return score


def daily_scores(items: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    """One row per calendar day: date, score, level, count (items due).

    `items` needs columns: date, course, type.
    """
    df = items.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    by_course = (
        df.groupby(["date", "course"])["type"].apply(list).apply(_score_group).rename("score").reset_index()
    )
    daily = by_course.groupby("date")["score"].sum()
    counts = df[df["type"].map(lambda t: TYPE_WEIGHTS.get(t, DEFAULT_WEIGHT) > 0)].groupby("date").size()

    start = pd.Timestamp(start).normalize() if start is not None else df["date"].min()
    end = pd.Timestamp(end).normalize() if end is not None else df["date"].max()
    days = pd.date_range(start, end, freq="D")
    out = pd.DataFrame({"date": days})
    out["score"] = out["date"].map(daily).fillna(0.0)
    out["count"] = out["date"].map(counts).fillna(0).astype(int)
    out["level"] = out["score"].apply(lambda s: level_for(s, DAILY_THRESHOLDS))
    return out


def course_daily_scores(items: pd.DataFrame) -> pd.DataFrame:
    """date, course, score: each class's contribution per day (for stacked views)."""
    df = items.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df.groupby(["date", "course"])["type"].apply(list).apply(_score_group).rename("score").reset_index()


def weekly_scores(daily: pd.DataFrame) -> pd.DataFrame:
    """Monday-start weeks: week_start, week_end, score, level, count."""
    d = daily.copy()
    d["week_start"] = d["date"] - pd.to_timedelta(d["date"].dt.weekday, unit="D")
    w = d.groupby("week_start").agg(score=("score", "sum"), count=("count", "sum")).reset_index()
    w["week_end"] = w["week_start"] + pd.Timedelta(days=6)
    w["level"] = w["score"].apply(lambda s: level_for(s, WEEKLY_THRESHOLDS))
    return w
