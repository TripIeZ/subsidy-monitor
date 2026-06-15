"""Монитор субсидированных билетов: скан -> сравнение с прошлым -> алерт в Telegram.

Запуск:
  python3 monitor.py --once     # один проход (для теста)
  python3 monitor.py            # вечный цикл с интервалом POLL_INTERVAL_SEC
"""
import asyncio
import datetime
import sys

from playwright.async_api import async_playwright

import config
import state
import ural
from notify import load_env, send

_MONTHS_SHORT = ["", "янв", "фев", "мар", "апр", "мая", "июн",
                 "июл", "авг", "сен", "окт", "ноя", "дек"]


def fmt_date(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d.day} {_MONTHS_SHORT[d.month]}"


def available_dates(merged):
    return sorted(d for d, p in merged.items()
                  if p is not None and p < config.SUBSIDY_PRICE_MAX)


def build_alert(route, new_dates, merged, first_time):
    head = "🎉 <b>Субсидия!</b>" if not first_time else "✅ <b>Старт мониторинга</b>"
    lines = [f"{head} {route['label']} · Ural"]
    shown = new_dates[:8]
    for d in shown:
        lines.append(f"• {fmt_date(d)} — от {merged[d]} ₽")
    if len(new_dates) > len(shown):
        lines.append(f"…и ещё {len(new_dates) - len(shown)} дат")
    url = ural.subsidized_url(route["orig"], route["dest"], new_dates[0])
    lines.append(f'\n<a href="{url}">Открыть на сайте Ural →</a>')
    return "\n".join(lines)


async def run_once():
    st = state.load()
    start = datetime.date.today() + datetime.timedelta(days=1)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=config.HEADLESS)
        ctx = await browser.new_context(locale="ru-RU", user_agent=ural.UA,
                                        viewport={"width": 1400, "height": 950})
        for route in config.ROUTES:
            if "ural" not in route.get("carriers", []):
                continue
            anchors = ural.anchors_for(start, config.MONTHS_AHEAD)
            merged = await ural.check_route(ctx, route, anchors, concurrency=5)
            avail = available_dates(merged)

            prev_rec = st.get(route["id"])
            prev = set(prev_rec["available"]) if prev_rec else set()
            new = [d for d in avail if d not in prev]
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{ts}] {route['label']}: доступно {len(avail)}, новых {len(new)}")

            if new:
                send(build_alert(route, new, merged, first_time=prev_rec is None))
            st[route["id"]] = {
                "available": avail,
                "updated": datetime.datetime.now().isoformat(timespec="seconds"),
            }
            state.save(st)
        await browser.close()


async def main():
    load_env()
    once = "--once" in sys.argv
    while True:
        try:
            await run_once()
        except Exception as e:
            print("cycle error:", repr(e))
        if once:
            break
        await asyncio.sleep(config.POLL_INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(main())
