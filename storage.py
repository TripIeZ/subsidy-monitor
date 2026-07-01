"""Хранение слежек пользователей бота (subscriptions.json).

Формат:
{
  "users": {
    "<chat_id>": {
      "watches": [
        {"id": "ab12cd34", "route": "hta_mow",
         "flex": "date|week|month", "value": "2026-08-14",
         "notified": ["2026-08-14"]}
      ]
    }
  }
}
"""
import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "subscriptions.json")


def _load():
    if not os.path.exists(PATH):
        return {"users": {}}
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("users", {})
            return data
    except (json.JSONDecodeError, OSError):
        return {"users": {}}


def _save(data):
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)


def get_watches(chat_id):
    return _load()["users"].get(str(chat_id), {}).get("watches", [])


def add_watch(chat_id, watch):
    data = _load()
    user = data["users"].setdefault(str(chat_id), {"watches": []})
    user["watches"].append(watch)
    _save(data)


def remove_watch(chat_id, watch_id):
    data = _load()
    user = data["users"].get(str(chat_id))
    if not user:
        return
    user["watches"] = [w for w in user["watches"] if w["id"] != watch_id]
    _save(data)


def set_notified(chat_id, watch_id, notified):
    data = _load()
    user = data["users"].get(str(chat_id))
    if not user:
        return
    for w in user["watches"]:
        if w["id"] == watch_id:
            w["notified"] = notified
    _save(data)


def all_users():
    """Возвращает {chat_id: {"watches": [...]}} — снимок для сканера."""
    return _load()["users"]
