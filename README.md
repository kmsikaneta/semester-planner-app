# Semester Planner

A web app that turns a whole semester (classes, assignments, exams, work, gym) into a daily workload graph, so students can see their heaviest weeks before they arrive.

## What it does
- Scores each day's workload from hours and difficulty
- Spreads effort over the days before exams and assignments
- Color-codes days (green, yellow, red) and marks peak days with stars
- Zoomable semester graph
- Morning brief: this week's load, next peak day, today's items, and items needing attention

## Built with
Python, pandas, Plotly, Streamlit

## How to run
    pip install pandas plotly streamlit numpy
    streamlit run app.py

## How the load score works
Effort = hours x (0.5 + 0.25 x difficulty). Exams spread over the 7 days before the date and assignments over 4 days, weighted toward the deadline. A day is a "peak" when its load is more than one standard deviation above the semester average.

## Roadmap
- Add-item form
- Mark items done
- Color-coded calendar view
- Syllabus upload to pull due dates automatically