import sys
import asyncio
from playwright.async_api import async_playwright
from ural import subsidized_url, UA

date = sys.argv[1] if len(sys.argv) > 1 else "2026-09-15"


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        ctx = await b.new_context(locale="ru-RU", user_agent=UA, viewport={"width": 1500, "height": 1100})
        page = await ctx.new_page()
        await page.goto(subsidized_url("HTA", "MOW", date), wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(7000)
        text = await page.evaluate("() => document.body.innerText")
        print("==== BODY TEXT (", date, ") ====")
        print("\n".join([l for l in text.split("\n") if l.strip()]))
        await page.screenshot(path="/tmp/ural/verify.png", full_page=True)
        print("\n[screenshot -> /tmp/ural/verify.png]")
        await b.close()

asyncio.run(main())
