"""Проверка дешёвых/субсидированных тарифов S7 через публичный API минимальных цен.

Без браузера, без капчи, без токенов:
    POST https://www.s7.ru/api/v1/minprice/calendars
отдаёт минимальную цену по каждой дате маршрута. Явного флага «субсидия» в данных
НЕТ — сигнал это ЦЕНА: когда S7 выкладывает субсидированную квоту, минимум дня
падает ниже коммерческого (~17 000 ₽). Порог отсева — config.S7_SUBSIDY_MAX.

Логика взята из отдельного репо s7-subsidy-monitor и оформлена как модуль
с тем же интерфейсом, что и ural.py (check_route -> {date_iso: price}).

httpx уже стоит как зависимость python-telegram-bot, отдельно ставить не нужно.
"""
import datetime
import urllib.parse

import httpx

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
API_URL = "https://www.s7.ru/api/v1/minprice/calendars"
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.s7.ru",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

_MAX_DEEP = 183  # лимит окна API за один запрос, дней вперёд


def search_url(orig, dest, date_iso):
    """Прямая ссылка на бронирование S7 на конкретную дату (для живого человека).

    Проверено 2026-07: редиректит на прелинкованный поиск ibe.s7.ru/air на нужную
    дату. Субсидию бот сам показать не может (капча в движке), поэтому это —
    точка передачи человеку: он открывает поиск и выбирает свою льготную категорию.
    """
    q = urllib.parse.urlencode({
        "searchType": "NORMAL", "journeySpan": "OW",
        "origin": orig, "destination": dest,
        "departureDate": date_iso, "returnDate": "",
        "numAdults": 1, "lang": "ru", "serviceType": "ibe", "CUR": "RUB",
    })
    return "https://www.s7.ru/external/s7-apps-redirect.dot?" + q


# Субсидию S7 нельзя вычитать из API — диплинк это ровно обычный поиск S7,
# внутри которого человек выбирает льготную категорию. Отдельное имя — для
# читаемости в боте.
subsidy_search_url = search_url


def _fetch_calendar(client, frm, to, start, deep):
    body = {"parameters": [{
        "currency": "RUB", "deep": deep, "from": frm, "to": to,
        "sorted": True, "startDate": start, "tripType": "OW", "group": "outbound",
    }]}
    headers = dict(HEADERS)
    headers["Referer"] = f"https://www.s7.ru/ru/flight/from/{frm}/to/{to}/"
    r = client.post(API_URL, json=body, headers=headers, timeout=30)
    r.raise_for_status()
    cals = r.json().get("calendars") or []
    return cals[0].get("minPrices", []) if cals else []


def check_route(orig, dest, months_ahead=4):
    """Возвращает {date_iso: price} — минимальная цена S7 по каждой дате окна.

    Синхронная (requests-подобная) функция; в асинхронном боте вызывать через
    asyncio.to_thread, чтобы не блокировать event loop.
    """
    start = datetime.date.today().isoformat()
    deep = min(max(months_ahead, 1) * 31, _MAX_DEEP)
    out = {}
    with httpx.Client() as client:
        for d in _fetch_calendar(client, orig, dest, start, deep):
            iso = d.get("outboundDate")
            price = d.get("price")
            if iso and price is not None:
                out[iso] = int(price)
    return out


if __name__ == "__main__":
    import sys
    o, dd = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("HTA", "MOW")
    prices = check_route(o, dd, months_ahead=4)
    cheapest = min(prices.values()) if prices else None
    print(f"S7 {o}->{dd}: дат {len(prices)}, минимум {cheapest} ₽")
    for iso in sorted(prices)[:12]:
        print(f"  {iso}  {prices[iso]} ₽")
