"""Интерактивный Telegram-бот «Радар субсидий».

Флоу пользователя (всё на кнопках, без ручного ввода):
  /start → «Начать слежку» → направление → гибкость дат → дата/неделя/месяц
  → слежка создана. Когда сканер находит субсидию под слежку — шлёт алерт.

Запуск:
  python bot.py
"""
import asyncio
import calendar as _cal
import datetime
import logging
from datetime import date, timedelta
from uuid import uuid4

from playwright.async_api import async_playwright
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, BotCommand
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
)

import config
import s7
import storage
import ural
from notify import load_env

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s | %(message)s", level=logging.INFO
)
log = logging.getLogger("bot")

ROUTE_BY_ID = {r["id"]: r for r in config.ROUTES}

_GEN = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря"]
_NOM = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
_SHORT = ["", "янв", "фев", "мар", "апр", "мая", "июн",
          "июл", "авг", "сен", "окт", "ноя", "дек"]

WELCOME = (
    "✈️ <b>Радар субсидий</b>\n\n"
    "Ловлю субсидированные билеты <b>Чита ↔ Москва</b> "
    "(S7 и Уральские авиалинии) и пишу сразу, как только они появятся в продаже.\n\n"
    "Обычный билет ~22 972 ₽, субсидия ~6 200 ₽ — <b>экономия ~16 000 ₽</b>.\n\n"
    "Субсидия положена льготным категориям: пенсионеры, молодёжь до 23, "
    "многодетные семьи, инвалиды.\n\n"
    "Жми «Начать слежку» — настроим за пару шагов 👇"
)

HOW = (
    "❓ <b>Как это работает</b>\n\n"
    "1. Ты выбираешь направление и когда хочешь улететь "
    "(точная дата, любой день недели или месяца).\n"
    "2. Я регулярно проверяю <b>Уральские авиалинии</b> и <b>S7</b>.\n"
    "3. Как только под твою слежку появляется субсидированный (или аномально "
    "дешёвый на S7) билет — мгновенно присылаю цену и ссылку на покупку.\n\n"
    "⚡️ Субсидия разлетается за минуты — бронируй сразу, как пришёл алерт."
)


# ───────────────────────── helpers ─────────────────────────

def fmt_full(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {_GEN[d.month]}"


def fmt_short(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {_SHORT[d.month]}"


def describe_route(rid):
    return ROUTE_BY_ID[rid]["label"]


def describe_value(flex, value):
    if flex == "date":
        return fmt_full(value)
    if flex == "month":
        y, m = value.split("-")
        return f"{_NOM[int(m)]} {y}"
    if flex == "week":
        start = date.fromisoformat(value)
        end = start + timedelta(days=6)
        if start.month == end.month:
            return f"{start.day}–{end.day} {_GEN[end.month]}"
        return f"{start.day} {_GEN[start.month]} – {end.day} {_GEN[end.month]}"
    return value


def watch_line(w):
    arrow = "🗓" if w["flex"] != "date" else "📅"
    return f"{describe_route(w['route'])} · {arrow} {describe_value(w['flex'], w['value'])}"


async def show(update, text, kb):
    """Редактирует сообщение (если это callback) или шлёт новое."""
    markup = InlineKeyboardMarkup(kb)
    if update.callback_query:
        await update.callback_query.message.edit_text(
            text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True
        )


# ───────────────────────── screens ─────────────────────────

def kb_main():
    return [
        [InlineKeyboardButton("🔔 Начать слежку", callback_data="new")],
        [InlineKeyboardButton("📋 Мои слежки", callback_data="my")],
        [InlineKeyboardButton("❓ Как это работает", callback_data="how")],
    ]


def screen_direction():
    kb = [
        [InlineKeyboardButton("➡️ Чита → Москва", callback_data="dir:hta_mow")],
        [InlineKeyboardButton("⬅️ Москва → Чита", callback_data="dir:mow_hta")],
        [InlineKeyboardButton("🔁 Туда и обратно", callback_data="dir:round")],
        [InlineKeyboardButton("‹ В меню", callback_data="menu")],
    ]
    return "Куда летим? Выбери направление:", kb


def screen_flex():
    kb = [
        [InlineKeyboardButton("📅 Точная дата", callback_data="flex:date")],
        [InlineKeyboardButton("🗓 Любой день недели", callback_data="flex:week")],
        [InlineKeyboardButton("📆 Любой день месяца", callback_data="flex:month")],
        [InlineKeyboardButton("‹ Назад", callback_data="new")],
    ]
    return ("Когда хочешь улететь?\n\n"
            "<i>Чем гибче даты — тем выше шанс поймать субсидию.</i>"), kb


def upcoming_months():
    today = date.today()
    out, y, m = [], today.year, today.month
    for _ in range(config.MONTHS_AHEAD + 1):
        out.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def screen_month():
    rows = []
    for y, m in upcoming_months():
        rows.append([InlineKeyboardButton(
            f"{_NOM[m]} {y}", callback_data=f"month:{y}-{m:02d}")])
    rows.append([InlineKeyboardButton("‹ Назад", callback_data="back_flex")])
    return "Выбери месяц — слежу за любым днём в нём:", rows


def screen_calendar(year, month, mode="date"):
    today = date.today()
    lo = today + timedelta(days=1)
    hi = today + timedelta(days=config.MONTHS_AHEAD * 31)

    prev_last = date(year, month, 1) - timedelta(days=1)
    nm_y, nm_m = (year + 1, 1) if month == 12 else (year, month + 1)
    next_first = date(nm_y, nm_m, 1)

    prev_cb = (f"cal:{mode}:{prev_last.year}-{prev_last.month:02d}"
               if prev_last >= date(today.year, today.month, 1) else "noop")
    next_cb = f"cal:{mode}:{nm_y}-{nm_m:02d}" if next_first <= hi else "noop"

    rows = [[
        InlineKeyboardButton("‹", callback_data=prev_cb),
        InlineKeyboardButton(f"{_NOM[month]} {year}", callback_data="noop"),
        InlineKeyboardButton("›", callback_data=next_cb),
    ], [InlineKeyboardButton(d, callback_data="noop")
        for d in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")]]

    day_prefix = "wday" if mode == "week" else "day"
    for week in _cal.Calendar(firstweekday=0).monthdayscalendar(year, month):
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="noop"))
                continue
            d = date(year, month, day)
            if lo <= d <= hi:
                row.append(InlineKeyboardButton(str(day), callback_data=f"{day_prefix}:{d.isoformat()}"))
            else:
                row.append(InlineKeyboardButton("·", callback_data="noop"))
        rows.append(row)
    rows.append([InlineKeyboardButton("‹ Назад", callback_data="back_flex")])
    title = ("Нажми любой день — буду следить за всю его неделю (Пн–Вс):"
             if mode == "week" else "Выбери дату вылета:")
    return title, rows


# ───────────────────────── handlers ─────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show(update, WELCOME, kb_main())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HOW, parse_mode="HTML")


async def cmd_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["draft"] = {}
    text, kb = screen_direction()
    await show(update, text, kb)


async def cmd_my(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await render_my(update, update.effective_chat.id)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    await q.answer()

    if data == "noop":
        return
    if data == "menu":
        await show(update, WELCOME, kb_main())
        return
    if data == "how":
        kb = [[InlineKeyboardButton("‹ В меню", callback_data="menu")]]
        await show(update, HOW, kb)
        return
    if data == "new":
        context.user_data["draft"] = {}
        text, kb = screen_direction()
        await show(update, text, kb)
        return
    if data == "my":
        await render_my(update, update.effective_chat.id)
        return

    if data.startswith("dir:"):
        choice = data.split(":", 1)[1]
        routes = ["hta_mow", "mow_hta"] if choice == "round" else [choice]
        context.user_data.setdefault("draft", {})["routes"] = routes
        text, kb = screen_flex()
        await show(update, text, kb)
        return

    if data == "back_flex":
        text, kb = screen_flex()
        await show(update, text, kb)
        return

    if data.startswith("flex:"):
        flex = data.split(":", 1)[1]
        context.user_data.setdefault("draft", {})["flex"] = flex
        if flex == "month":
            text, kb = screen_month()
        else:
            today = date.today()
            text, kb = screen_calendar(today.year, today.month, flex)
        await show(update, text, kb)
        return

    if data.startswith("cal:"):
        _, mode, ym = data.split(":", 2)
        y, m = map(int, ym.split("-"))
        text, kb = screen_calendar(y, m, mode)
        await show(update, text, kb)
        return

    if data.startswith("day:"):
        await save_watch(update, context, "date", data.split(":", 1)[1])
        return
    if data.startswith("wday:"):
        d = date.fromisoformat(data.split(":", 1)[1])
        monday = d - timedelta(days=d.weekday())
        await save_watch(update, context, "week", monday.isoformat())
        return
    if data.startswith("month:"):
        await save_watch(update, context, "month", data.split(":", 1)[1])
        return

    if data.startswith("del:"):
        storage.remove_watch(update.effective_chat.id, data.split(":", 1)[1])
        await render_my(update, update.effective_chat.id)
        return


async def save_watch(update, context, flex, value):
    draft = context.user_data.get("draft", {})
    routes = draft.get("routes", [])
    if not routes:
        text, kb = screen_direction()
        await show(update, text, kb)
        return

    chat_id = update.effective_chat.id
    for rid in routes:
        storage.add_watch(chat_id, {
            "id": uuid4().hex[:8], "route": rid,
            "flex": flex, "value": value, "notified": {},
        })

    if len(routes) == 2:
        route_txt = "Чита ↔ Москва (туда и обратно)"
    else:
        route_txt = describe_route(routes[0])
    when = describe_value(flex, value)
    text = (
        "✅ <b>Слежу за билетами!</b>\n\n"
        f"✈️ {route_txt}\n"
        f"🗓 {when}\n\n"
        "Как только появится субсидия — сразу напишу.\n"
        "Можешь добавить ещё слежку или посмотреть текущие."
    )
    kb = [
        [InlineKeyboardButton("➕ Ещё слежка", callback_data="new")],
        [InlineKeyboardButton("📋 Мои слежки", callback_data="my")],
    ]
    context.user_data["draft"] = {}
    await show(update, text, kb)


async def render_my(update, chat_id):
    watches = storage.get_watches(chat_id)
    if not watches:
        text = "📋 У тебя пока нет слежек.\n\nНажми «Начать слежку», чтобы добавить."
        kb = [[InlineKeyboardButton("🔔 Начать слежку", callback_data="new")],
              [InlineKeyboardButton("‹ В меню", callback_data="menu")]]
        await show(update, text, kb)
        return
    text = (f"📋 <b>Твои слежки ({len(watches)}):</b>\n\n"
            "Нажми на слежку, чтобы удалить её.")
    kb = [[InlineKeyboardButton(f"🗑 {watch_line(w)}", callback_data=f"del:{w['id']}")]
          for w in watches]
    kb.append([InlineKeyboardButton("➕ Новая слежка", callback_data="new")])
    kb.append([InlineKeyboardButton("‹ В меню", callback_data="menu")])
    await show(update, text, kb)


# ───────────────────────── matching + scanner ─────────────────────────

def watch_matches(flex, value, iso):
    if flex == "date":
        return iso == value
    if flex == "month":
        return iso.startswith(value)
    if flex == "week":
        start = date.fromisoformat(value)
        d = date.fromisoformat(iso)
        return 0 <= (d - start).days <= 6
    return False


async def scan_routes(route_ids):
    start = date.today() + timedelta(days=1)
    results = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=config.HEADLESS)
        ctx = await browser.new_context(locale="ru-RU", user_agent=ural.UA,
                                        viewport={"width": 1400, "height": 950})
        for rid in route_ids:
            route = ROUTE_BY_ID[rid]
            anchors = ural.anchors_for(start, config.MONTHS_AHEAD)
            results[rid] = await ural.check_route(ctx, route, anchors, concurrency=5)
        await browser.close()
    return results


_CARRIER_LABEL = {"ural": "Ural", "s7": "S7"}


def _notified_map(w):
    """notified бывает старым списком (Ural-only) или словарём по перевозчикам."""
    n = w.get("notified")
    if isinstance(n, dict):
        return {k: list(v) for k, v in n.items()}
    if isinstance(n, list):
        return {"ural": list(n)}
    return {}


async def send_alert(bot, chat_id, w, carrier, dates):
    route = ROUTE_BY_ID[w["route"]]
    ds = sorted(dates)
    if carrier == "s7":
        head = "🟢 <b>Дешёвый/субсидированный билет S7!</b>"
        url = s7.search_url(route["orig"], route["dest"], ds[0])
    else:
        head = "🎉 <b>Субсидия найдена!</b>"
        url = ural.subsidized_url(route["orig"], route["dest"], ds[0])
    lines = [head, f"✈️ {route['label']} · {_CARRIER_LABEL.get(carrier, carrier)}", ""]
    for iso in ds[:8]:
        lines.append(f"• {fmt_full(iso)} — <b>{dates[iso]} ₽</b>")
    if len(ds) > 8:
        lines.append(f"…и ещё {len(ds) - 8} дат")
    lines.append("\n⚡️ Разлетается за минуты — бронируй сейчас!")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎫 Купить на сайте", url=url)],
        [InlineKeyboardButton("🔕 Нашёл билет, остановить", callback_data=f"del:{w['id']}")],
    ])
    await bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML",
                           reply_markup=kb, disable_web_page_preview=True)


async def scan_and_notify(app):
    users = storage.all_users()
    route_ids = {w["route"] for u in users.values() for w in u["watches"]}
    if not route_ids:
        return
    log.info("scan: маршрутов в работе %d", len(route_ids))

    # avail[(route_id, carrier)] = {iso: price} — доступные дешёвые/субсидированные даты
    avail = {}

    # Ural — через браузер (Playwright)
    ural_routes = [rid for rid in route_ids
                   if "ural" in ROUTE_BY_ID[rid].get("carriers", [])]
    if ural_routes:
        try:
            results = await scan_routes(ural_routes)
            for rid, m in results.items():
                avail[(rid, "ural")] = {iso: pr for iso, pr in m.items()
                                        if pr is not None and pr < config.SUBSIDY_PRICE_MAX}
        except Exception as e:
            log.warning("ural scan error: %r", e)

    # S7 — через публичный API (без браузера), в отдельном потоке чтобы не блокировать loop
    for rid in route_ids:
        if "s7" not in ROUTE_BY_ID[rid].get("carriers", []):
            continue
        route = ROUTE_BY_ID[rid]
        try:
            prices = await asyncio.to_thread(
                s7.check_route, route["orig"], route["dest"], config.MONTHS_AHEAD)
            avail[(rid, "s7")] = {iso: pr for iso, pr in prices.items()
                                  if pr is not None and pr <= config.S7_SUBSIDY_MAX}
            log.info("s7 %s: дней ≤%d ₽: %d", rid, config.S7_SUBSIDY_MAX,
                     len(avail[(rid, "s7")]))
        except Exception as e:
            log.warning("s7 scan error %s: %r", rid, e)

    for chat_id, u in users.items():
        for w in u["watches"]:
            notified = _notified_map(w)
            for carrier in ROUTE_BY_ID[w["route"]].get("carriers", []):
                a = avail.get((w["route"], carrier))
                if a is None:
                    continue
                matched = [iso for iso in a if watch_matches(w["flex"], w["value"], iso)]
                already = set(notified.get(carrier, []))
                new = [iso for iso in matched if iso not in already]
                if new:
                    try:
                        await send_alert(app.bot, int(chat_id), w, carrier,
                                         {iso: a[iso] for iso in new})
                        log.info("alert -> %s: %s/%s (%d дат)",
                                 chat_id, w["route"], carrier, len(new))
                    except Exception as e:
                        log.warning("send fail %s: %r", chat_id, e)
                notified[carrier] = sorted(set(matched))  # только актуальные
            storage.set_notified(chat_id, w["id"], notified)


async def scan_loop(app):
    await asyncio.sleep(5)  # дать боту подняться
    while True:
        try:
            await scan_and_notify(app)
        except Exception as e:
            log.warning("scan cycle error: %r", e)
        await asyncio.sleep(config.POLL_INTERVAL_SEC)


async def on_startup(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Меню"),
        BotCommand("new", "Новая слежка"),
        BotCommand("my", "Мои слежки"),
        BotCommand("help", "Как это работает"),
    ])
    app.create_task(scan_loop(app))
    log.info("бот запущен, фоновый сканер активен")


def main():
    load_env()
    import os
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Не задан TELEGRAM_BOT_TOKEN в .env")

    app = Application.builder().token(token).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("my", cmd_my))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
