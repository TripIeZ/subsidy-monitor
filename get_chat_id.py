#!/usr/bin/env python3
"""Узнать свой chat_id.

Шаги:
  1. Впиши TELEGRAM_BOT_TOKEN в .env
  2. Открой СВОЕГО бота в Telegram (имя покажет этот скрипт), нажми Start / напиши ему
  3. Запусти: python3 get_chat_id.py
"""
import json
import os
import urllib.request

from notify import load_env

load_env()
token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not token:
    raise SystemExit("Сначала впиши TELEGRAM_BOT_TOKEN в .env")


def api(method):
    url = f"https://api.telegram.org/bot{token}/{method}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        return json.load(resp)


# 1. Какому боту принадлежит токен
me = api("getMe")
if not me.get("ok"):
    raise SystemExit(f"Токен не принят Telegram: {me}")
bot = me["result"]
username = bot.get("username")
print(f"Токен принадлежит боту: @{username}  (имя: {bot.get('first_name')})")
print(f"  -> в Telegram открой ИМЕННО @{username} и напиши ему /start или 'привет'\n")

# 2. Сообщения, присланные этому боту
data = api("getUpdates")
updates = data.get("result", [])
if not updates:
    print(f"Входящих сообщений боту @{username} пока нет.")
    print("Убедись, что пишешь именно ему (а не BotFather и не другому боту), потом запусти снова.")
else:
    seen = {}
    for u in updates:
        msg = u.get("message") or u.get("edited_message") or {}
        chat = msg.get("chat", {})
        if chat.get("id"):
            seen[chat["id"]] = chat.get("username") or chat.get("first_name") or ""
    print("Найденные chat_id:")
    for cid, who in seen.items():
        print(f"  {cid}  ({who})")
    print("\nВпиши нужный в .env как TELEGRAM_CHAT_ID")
