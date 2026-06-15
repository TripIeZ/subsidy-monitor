#!/usr/bin/env python3
"""Отправка алертов в Telegram. Зависимостей нет — работает на системном python3."""
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load_env(path=ENV_PATH):
    """Минимальный парсер .env (KEY=VALUE построчно)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def send(text, parse_mode="HTML"):
    """Шлёт сообщение в Telegram. Возвращает (ok, response_text)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise SystemExit(
            "Не заданы TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID.\n"
            "Заполни их в файле .env рядом со скриптом."
        )
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return True, resp.read().decode()
    except urllib.error.HTTPError as e:
        return False, e.read().decode()


if __name__ == "__main__":
    load_env()
    msg = sys.argv[1] if len(sys.argv) > 1 else (
        "✅ <b>subsidy-monitor</b> подключён.\n"
        "Сюда будут падать алерты о субсидированных билетах Чита ↔ Москва."
    )
    ok, resp = send(msg)
    if ok:
        print("Отправлено! Проверь Telegram.")
    else:
        print("Ошибка отправки:\n" + resp)
        sys.exit(1)
