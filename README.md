# Semester Planner

A web app that turns a whole semester (classes, assignments, exams, work, gym) into a daily workload graph, so students can see their heaviest weeks before they arrive.

## What it does
- Scores how busy each day is from what's due that day
- Five busyness levels (open, calm, steady, busy, peak), green to soft coral
- The whole semester as one graph at the top of the dashboard, by week or by day, with peaks labeled by their cause
- Morning brief: this week's load, next peak day, today's items, and items needing attention

## Built with
Python, pandas, Plotly, Streamlit

## How to run
    pip install pandas plotly streamlit numpy
    streamlit run app.py

## How busyness works
See `busyness.py`. Each item counts on its due date: exam 4, quiz 3, assignment 2, reading or job 1, class meetings 0. Many items from one class on one day count as one heavy day (first item full, +0.5 per extra, capped at +4). Daily levels: open 0, calm under 4, steady 4 to 6.5, busy 7 to 9.5, peak 10+. Weekly: calm under 10, steady 10 to 14.5, busy 15 to 20.5, peak 21+. Starting values; tune on real semesters.

## Roadmap
- Add-item form
- Mark items done
- Color-coded calendar view
- Syllabus upload to pull due dates automatically