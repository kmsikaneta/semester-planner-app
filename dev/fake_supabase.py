"""An in-memory stand-in for the Supabase client, so the app can run with no keys.

Used only by dev/preview.py. Data comes from a CSV (date, course, title, type,
hours, difficulty, done) and lives in memory until you stop the preview.
"""
from __future__ import annotations

import copy
import csv
import os
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[1]
_DATA = Path(os.environ.get("PREVIEW_DATA", _ROOT / "sample_items.csv"))

DEMO_USER = SimpleNamespace(
    id="demo-user", email="demo@student.edu",
    user_metadata={"full_name": os.environ.get("PREVIEW_NAME", "Sunny")},
)
DEMO_SESSION = SimpleNamespace(access_token="demo", refresh_token="demo")

_ROWS: list[dict] = []


def _load():
    if _ROWS:
        return
    with open(_DATA, newline="") as f:
        for i, r in enumerate(csv.DictReader(f), start=1):
            _ROWS.append({
                "id": i, "user_id": DEMO_USER.id, "course": r.get("course") or "General",
                "date": r["date"], "title": r["title"], "type": r.get("type") or "assignment",
                "hours": float(r.get("hours") or 1.5), "difficulty": int(r.get("difficulty") or 3),
                "done": r.get("done") or "no",
            })


class _Query:
    def __init__(self, op, payload=None):
        self.op, self.payload, self.filters = op, payload, []

    def select(self, *_):
        return self

    def eq(self, col, val):
        self.filters.append(lambda r: str(r.get(col)) == str(val))
        return self

    def in_(self, col, vals):
        vals = {str(v) for v in vals}
        self.filters.append(lambda r: str(r.get(col)) in vals)
        return self

    def _match(self):
        return [r for r in _ROWS if all(f(r) for f in self.filters)]

    def execute(self):
        _load()
        if self.op == "select":
            return SimpleNamespace(data=copy.deepcopy(self._match()))
        if self.op == "update":
            for r in self._match():
                r.update(self.payload)
            return SimpleNamespace(data=[])
        if self.op == "delete":
            keep = [r for r in _ROWS if not all(f(r) for f in self.filters)]
            _ROWS[:] = keep
            return SimpleNamespace(data=[])
        if self.op == "insert":
            next_id = max((r["id"] for r in _ROWS), default=0) + 1
            for i, row in enumerate(self.payload):
                _ROWS.append({"id": next_id + i, **row})
            return SimpleNamespace(data=[])
        raise ValueError(self.op)


class _Table:
    def select(self, *a):
        return _Query("select")

    def update(self, payload):
        return _Query("update", payload)

    def delete(self):
        return _Query("delete")

    def insert(self, rows):
        return _Query("insert", rows)


class _Auth:
    def set_session(self, *_):
        pass

    def update_user(self, attrs):
        if "data" in attrs:
            DEMO_USER.user_metadata = {**DEMO_USER.user_metadata, **attrs["data"]}
        return SimpleNamespace(user=DEMO_USER)

    def sign_in_with_password(self, *_):
        return SimpleNamespace(user=DEMO_USER, session=DEMO_SESSION)

    sign_up = sign_in_with_password

    def sign_out(self):
        pass

    def reset_password_for_email(self, *a, **k):
        pass

    def exchange_code_for_session(self, *_):
        return SimpleNamespace(user=None, session=None)

    verify_otp = exchange_code_for_session


class _Client:
    auth = _Auth()

    def table(self, _name):
        return _Table()


def create_client(*_):
    return _Client()
