"""Run the app with no Supabase or Gemini keys, on sample data.

    streamlit run dev/preview.py
    PREVIEW_DATA=path/to/items.csv streamlit run dev/preview.py   # your own CSV
    PREVIEW_LOGIN=1 streamlit run dev/preview.py                  # start on the sign-in screen

Everything you change lives in memory and resets when you stop it.
AI features (quick add, syllabus, Study coach) need a real GEMINI_API_KEY.
"""
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev"))

import fake_supabase  # noqa: E402

sys.modules["supabase"] = fake_supabase

import streamlit as st  # noqa: E402

st.secrets = {  # type: ignore[assignment]
    "SUPABASE_URL": "preview", "SUPABASE_KEY": "preview",
    "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", "missing"),
}

if not os.environ.get("PREVIEW_LOGIN") and st.session_state.get("user") is None:
    st.session_state["user"] = fake_supabase.DEMO_USER
    st.session_state["session"] = fake_supabase.DEMO_SESSION

runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
