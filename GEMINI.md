# Rules for any AI assistant editing this repo

Two people (Kaya and Sunny) edit this app, often through AI assistants. Work has been lost three times because an assistant rewrote `app.py` from an old copy it remembered. Follow these rules every time.

1. **Read the current files from disk before changing anything.** Never rebuild a file from memory or from earlier in the conversation. The version on disk is the only truth; someone else may have changed it since you last saw it.
2. **Make small, targeted edits.** Change only the lines your task needs. Never output or save a whole new `app.py`.
3. **Before you commit, check the diff.** If it deletes code you weren't asked to touch, stop and tell the person instead of committing. A healthy change adds and removes only what the task describes.
4. **Get the latest first.** Run `git pull` before starting work, and again right before you push.
5. **Never force-push** (`git push --force`) and never reset `main`.

## Where things live
- `app.py`: data, sign-in, AI helpers and the pages
- `busyness.py`: how busy each day is (Kaya owns the math)
- `weather.py`: busyness levels as weather (Clear, Fair, Overcast, Rain, Storm), icons, the brief's sky
- `styles.css`: all styling. Don't put CSS inside `app.py`
- `dev/preview.py`: runs the app on sample data with no keys (`streamlit run dev/preview.py`)

## Design rules the code must keep
- The semester graph is the first and biggest thing on Home.
- Green-to-coral colors mean busyness only. Classes use blue, indigo, violet, pink and teal.
- Busyness counts what's due on its due date. Hours and difficulty never drive the graph.
