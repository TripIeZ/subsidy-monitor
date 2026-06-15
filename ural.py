"""Проверка субсидированных мест у Уральских авиалиний.

Без серых схем: строим обычный deep-link booking-движка
book.uralairlines.ru/?model=<JSON> с субсидированным тарифом и читаем РЕНДЕР.
Лента дат на странице показывает ~9 дней с ценой за раз:
  «от 6 200 ₽»  — субсидия доступна
  «от 22 972 ₽» — раскуплено (обычный тариф)
  «-»           — рейса нет
Поэтому сканируем окно якорями с шагом ~7 дней — месяц за 4-5 загрузок.
"""
import asyncio
import copy
import datetime
import json
import re
import urllib.parse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

_WEEKDAYS = {"ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"}
_MONTHS = {"январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
           "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12}
_PRICE_RE = re.compile(r"(\d[\d\s ]+)\s*₽")

# Подтверждённая живьём модель субсидированного поиска (subsidyType=3).
_BASE = {
    "departureDate": None, "returnDate": None,
    "departureLocation": "HTA", "arrivalLocation": "MOW",
    "displayType": 2, "tripType": "O", "promo": None,
    "passengers": [{
        "passengerNum": 1, "type": "pensioner", "hasInfant": False,
        "isSubsidizedType": True, "isSubsidizedFedType": False, "isPreferentialFedType": False,
        "isDisabledSubsidizedType": False, "isKaliningradSubsidizedType": False,
        "isFarEastSubsidizedType": False, "isAgeSubsidizedType": True, "canHavePrivileges": True,
    }],
    "sessionMarker": None, "isPrivileges": False, "flights": [], "subsidyType": 3,
    "language": "RU", "metaSearchEngine": None, "currency": "RUB", "operation": "booking",
    "error": None, "validationFieldsErrors": None, "isInvalid": False,
    "certificateNumber": None, "certificateSurname": None, "login": None, "token": None,
}


def subsidized_url(orig, dest, date_iso):
    m = copy.deepcopy(_BASE)
    m["departureLocation"] = orig
    m["arrivalLocation"] = dest
    m["departureDate"] = date_iso + "T00:00:00"
    js = json.dumps(m, ensure_ascii=False, separators=(",", ":"))
    return "https://book.uralairlines.ru/?model=" + urllib.parse.quote(js, safe="")


def _to_iso(month, day, anchor):
    for y in (anchor.year, anchor.year + 1, anchor.year - 1):
        try:
            d = datetime.date(y, month, day)
        except ValueError:
            continue
        if abs((d - anchor).days) <= 20:
            return d.isoformat()
    return None


def parse_strip(text, anchor):
    """Из текста страницы достаём {date_iso: price|None} по ленте дат вокруг anchor."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    out = {}
    i = 0
    while i < len(lines) - 3:
        if lines[i] in _WEEKDAYS and lines[i + 1].isdigit() and lines[i + 2].lower() in _MONTHS:
            day = int(lines[i + 1])
            mon = _MONTHS[lines[i + 2].lower()]
            val = lines[i + 3]
            iso = _to_iso(mon, day, anchor)
            price = None
            pm = _PRICE_RE.search(val)
            if pm:
                price = int(re.sub(r"\D", "", pm.group(1)))
            if iso:
                out[iso] = price
            i += 4
        else:
            i += 1
    return out


async def _scan_anchor(context, orig, dest, anchor, sem):
    async with sem:
        page = await context.new_page()
        try:
            await page.goto(subsidized_url(orig, dest, anchor.isoformat()),
                            wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(6000)
            text = await page.evaluate("() => document.body.innerText")
            return parse_strip(text, anchor)
        except Exception as e:
            return {"_error_" + anchor.isoformat(): str(e)[:100]}
        finally:
            await page.close()


async def check_route(context, route, anchors, concurrency=5):
    """Возвращает {date_iso: price|None} по всему окну (объединение лент)."""
    sem = asyncio.Semaphore(concurrency)
    parts = await asyncio.gather(
        *[_scan_anchor(context, route["orig"], route["dest"], a, sem) for a in anchors]
    )
    merged = {}
    for part in parts:
        for k, v in part.items():
            if k.startswith("_error_"):
                continue
            # запись с ценой важнее записи без цены
            if k not in merged or (v is not None and merged[k] is None):
                merged[k] = v
    return merged


def anchors_for(start, months_ahead, step_days=7):
    end = start + datetime.timedelta(days=months_ahead * 31)
    out, d = [], start
    while d <= end:
        out.append(d)
        d += datetime.timedelta(days=step_days)
    return out


if __name__ == "__main__":
    from playwright.async_api import async_playwright

    async def main():
        async with async_playwright() as p:
            b = await p.chromium.launch(headless=True)
            ctx = await b.new_context(locale="ru-RU", user_agent=UA,
                                      viewport={"width": 1400, "height": 950})
            anchors = [datetime.date(2026, 9, 15), datetime.date(2026, 9, 22)]
            merged = await check_route(ctx, {"orig": "HTA", "dest": "MOW"}, anchors, concurrency=3)
            for iso in sorted(merged):
                p_ = merged[iso]
                tag = "СУБСИДИЯ" if (p_ and p_ < 15000) else ("раскуплено" if p_ else "нет рейса")
                print(f"  {iso}  {str(p_):>8}  {tag}")
            await b.close()

    asyncio.run(main())
