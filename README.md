# Semester Planner (working name: Plantech)

See your whole semester as one line. The app turns a Canvas calendar feed and your syllabi into a busyness graph, so the hard weeks are visible before they arrive.

## Before you edit (read this, Kaya and Sunny)
1. **Pull first, every time:** `git pull` (or open the file fresh on GitHub) right before you change anything. Editing an old copy of `app.py` and pushing it erases whatever was merged since.
2. **Work on a branch and open a PR.** Don't push straight to `main`; `main` is what the live app runs.
3. Design lives in `styles.css` and `weather.py`; busyness math lives in `busyness.py`; `app.py` is data, auth, AI and pages.

## Pages
- **Home:** the semester graph (hero), this week's strip, and Today's brief with check-offs
- **Semester:** the graph by week, by day, or by class, plus the heaviest weeks
- **Calendar:** month view; only busy and stormy days get color
- **Tasks:** everything due, grouped by day, with check-offs and a table mode for bulk edits
- **Classes:** progress per class, syllabus totals, colors, rename, delete
- **Study coach:** AI 7-day plan (runs in the background)
- **Add & sync:** Canvas calendar link, syllabus reader, quick add, one item
- **Settings**

## How busyness works
See `busyness.py`. Each item counts on its due date: exam 4, quiz 3, assignment 2, reading or event 1, class meetings 0. Many items from one class on one day count as one heavy day (first item full, +0.5 per extra, capped at +4).

## The weather world
Every busyness level is weather: open = Clear, calm = Fair, steady = Overcast, busy = Rain, peak = Storm (`weather.py`). Icons appear next to busyness labels, and Today's brief sits under that day's sky. Drop the Higgsfield art into `assets/skies/` as `clear.png`, `fair.png`, `overcast.png`, `rain.png`, `storm.png` and the brief uses it automatically; until then a code-drawn version of the same hills stands in.

## Run it
    pip install -r requirements.txt
    streamlit run app.py            # needs .streamlit/secrets.toml (Supabase + Gemini)

Preview with no keys, on sample data (changes reset when you stop it):

    streamlit run dev/preview.py
    PREVIEW_DATA=my_items.csv streamlit run dev/preview.py

Built with Python, pandas, Plotly, Streamlit, Supabase and Gemini.
