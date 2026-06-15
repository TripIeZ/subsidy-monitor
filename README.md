# subsidy-monitor

Мониторинг **субсидированных** авиабилетов с алертом в Telegram, когда места
появляются в продаже. Сейчас покрыты Уральские авиалинии (обе стороны Чита ↔ Москва).

## Как это работает
- Строим обычный deep-link booking-движка Ural:
  `book.uralairlines.ru/?model=<JSON>` с субсидированным тарифом (`subsidyType=3`).
- Headless-браузер (Playwright) открывает страницу и **читает рендер**: лента дат
  показывает по ~9 дней с ценой — `от 6 200 ₽` (субсидия есть), `от 22 972 ₽`
  (раскуплено), `-` (рейса нет). Никаких приватных API и токенов.
- Сканируем окно якорями с шагом 7 дней → месяц за 4-5 загрузок.
- Сравниваем с прошлым проходом (`state.json`) и шлём в Telegram **только новые** даты.

## Установка с нуля (новый компьютер / контрибьютор)
```bash
git clone https://github.com/katanaim/subsidy-monitor.git
cd subsidy-monitor
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium   # скачает headless-браузер (~100 МБ)
cp .env.example .env                               # затем впиши токен и chat_id
```
Свой Telegram-бот: создай у **@BotFather** (`/newbot`), токен и `chat_id`
(через @userinfobot или `python3 get_chat_id.py`) впиши в `.env`.

## Запуск
```bash
cd subsidy-monitor
.venv/bin/python monitor.py --once   # один проход (тест)
.venv/bin/python monitor.py          # вечный цикл, раз в 30 мин (POLL_INTERVAL_SEC)
```
Для постоянной работы Mac должен быть включён и не спать (либо вынести на VPS /
поставить launchd-сервис).

## Настройка — config.py
- `ROUTES` — маршруты (добавляются одной строкой; MOW = все аэропорты Москвы).
- `MONTHS_AHEAD` — глубина сканирования (по умолчанию 4 мес).
- `POLL_INTERVAL_SEC` — частота проверки (1800 = 30 мин).
- `SUBSIDY_PRICE_MAX` — порог цены, ниже которого тариф считаем субсидированным.
- `HEADLESS` — False, чтобы видеть окно браузера (отладка).

## Файлы
| файл | назначение |
|------|-----------|
| `monitor.py` | главный цикл: скан → diff → алерт |
| `ural.py` | проверка Ural (deep-link + парсинг ленты дат) |
| `notify.py` | отправка в Telegram (без зависимостей) |
| `config.py` | маршруты и настройки |
| `state.py` | состояние между проверками (`state.json`) |
| `get_chat_id.py` | узнать свой Telegram chat_id |
| `verify.py` | дебаг: показать рендер субсидии на конкретную дату |

## Фазы
- [x] Фаза 1 — Telegram-канал
- [x] Фаза 2 — Ural, обе стороны Чита ↔ Москва
- [ ] Фаза 3 — S7 Airlines
- [ ] Фаза 4 — автозапуск 24/7 (launchd / VPS)
