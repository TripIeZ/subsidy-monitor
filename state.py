"""Состояние между проверками — чтобы слать алерт только на ИЗМЕНЕНИЯ.

Формат state.json:
{
  "hta_mow": {"available": ["2026-09-12", "2026-09-19"], "updated": "2026-06-15T12:00:00"},
  ...
}
"""
import json
import os

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")


def load():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save(state):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_PATH)
