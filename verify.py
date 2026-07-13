"""Живой дебаг рендера субсидии на конкретную дату и тип субсидии.

Запуск:
  python verify.py 2026-09-15            # тип по умолчанию (age)
  python verify.py 2026-09-15 dfo        # проверить дальневосточную субсидию
  python verify.py 2026-09-15 dfo HTA MOW

Печатает текст страницы booking-движка и кладёт скриншот рядом со скриптом.
Полезно, чтобы глазами убедиться, что модель нужного типа субсидии реально
отдаёт субсидированные цены (а не «нет рейсов» / обычный тариф).
"""
import os
import sys
import asyncio

from playwright.async_api import async_playwright

import config
from ural import subsidized_url, UA

date = sys.argv[1] if len(sys.argv) > 1 else "2026-09-15"
subsidy = sys.argv[2] if len(sys.argv) > 2 else config.DEFAULT_SUBSIDY
orig = sys.argv[3] if len(sys.argv) > 3 else "HTA"
dest = sys.argv[4] if len(sys.argv) > 4 else "MOW"

if subsidy not in config.URAL_SUBSIDIES:
    raise SystemExit(f"Неизвестный тип субсидии: {subsidy}. "
                     f"Доступно: {', '.join(config.URAL_SUBSIDIES)}")

SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify.png")


async def main():
    prof = config.URAL_SUBSIDIES[subsidy]
    print(f"Тип субсидии: {subsidy} ({prof['label']}) · {orig}->{dest} · {date}")
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        ctx = await b.new_context(locale="ru-RU", user_agent=UA,
                                  viewport={"width": 1500, "height": 1100})
        page = await ctx.new_page()
        await page.goto(subsidized_url(orig, dest, date, subsidy),
                        wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(7000)
        text = await page.evaluate("() => document.body.innerText")
        print("==== BODY TEXT ====")
        print("\n".join([l for l in text.split("\n") if l.strip()]))
        await page.screenshot(path=SHOT, full_page=True)
        print(f"\n[screenshot -> {SHOT}]")
        await b.close()

asyncio.run(main())
