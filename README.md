# Cineora QR

Cineora QR — Telegram ichida ishlaydigan to‘liq QR Studio Mini App. Aiogram 3 bot, aiohttp API va responsiv Web App bitta servisda ishlaydi.

## Imkoniyatlar

- 11+ QR turi: sayt, Wi‑Fi, telefon, matn, Telegram, email, SMS, WhatsApp, vCard kontakt, lokatsiya va taqvim tadbiri.
- Apple + Stripe uslubidagi light/dark interfeys, o‘zbek, rus va ingliz tillari.
- Jonli preview, rang va gradient, square/rounded/dots shakllari, ramka yozuvi va logotip.
- PNG va sifat yo‘qotmaydigan SVG yuklab olish, tizim Share oynasi orqali ulashish.
- QR skaner: `BarcodeDetector`, ishlamasa `jsQR` zaxira mexanizmi.
- PostgreSQL yoki SQLite tarix, sevimlilar, qayta tahrirlash va maxfiylik sozlamalari.
- Telegram `initData` imzosini serverda tekshirish, xavfsizlik sarlavhalari va flood himoyasi.
- Admin uchun `/stats`, Docker va Render qo‘llovi.

## Lokal ishga tushirish

Python 3.11 yoki 3.12 tavsiya qilinadi.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

Mini Appni Telegram tashqarisida lokal tekshirish uchun `.env` ichida `WEBAPP_PREVIEW=true` qiling. Productionda bu qiymat albatta `false` bo‘lishi kerak.

## Render deploy

Repository’ni Render Web Service’ga ulang:

| Parametr | Qiymat |
|---|---|
| Runtime | Docker |
| Start command | Dockerfile ichida (`python main.py`) |
| Health check | `/health` |
| Web App URL | `https://<service>.onrender.com` |

Environment qiymatlari:

| O‘zgaruvchi | Vazifasi | Standart |
|---|---|---|
| `BOT_TOKEN` | BotFather tokeni | Majburiy |
| `ADMIN_IDS` | `/stats` uchun Telegram IDlar | Bo‘sh |
| `DATABASE_URL` | PostgreSQL connection URL | Bo‘sh bo‘lsa SQLite |
| `DATABASE_PATH` | SQLite fayl manzili | `data/qrbot.sqlite3` |
| `WEBAPP_URL` | Mini Appning HTTPS manzili | Render URL’dan olinadi |
| `WEBAPP_PREVIEW` | Telegram tashqarisidagi test rejimi | `false` |
| `LOG_LEVEL` | Log darajasi | `INFO` |

Render Free fayl tizimi vaqtinchalik, shuning uchun production tarix uchun tashqi PostgreSQL ishlating. `DATABASE_URL` odatda `postgresql://...` yoki `postgres://...` formatida bo‘ladi.

Bot ishga tushganda Telegram menyu tugmasini avtomatik ravishda Mini Appga bog‘laydi. `WEBAPP_URL` bo‘lmasa, Render bergan `RENDER_EXTERNAL_URL` ishlatiladi.

## Docker

```bash
docker compose up -d --build
docker compose logs -f
```

## Test

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
pytest
ruff check .
node --check web/app.js
```

## Tuzilma

```text
app/
  bot.py          # bot va Web App server lifecycle
  webapp.py       # Mini App API, Telegram auth va statik fayllar
  db.py           # PostgreSQL/SQLite ma’lumotlar qatlami
  qr_builder.py   # maxsus PNG/SVG generator
  handlers.py     # Telegram bot menyulari
  payloads.py     # QR formatlari
  validators.py   # kiruvchi ma’lumot tekshiruvi
web/
  index.html      # Mini App interfeysi
  styles.css      # light/dark responsiv dizayn
  app.js          # QR Studio, tarix, skaner va lokalizatsiya
tests/            # 21 avtomatik test
```

## Xavfsizlik

- `.env`, token va baza connection URL’ini GitHub’ga yuklamang.
- Productionda `WEBAPP_PREVIEW=false` bo‘lsin.
- Wi‑Fi ma’lumotlarini tarixga saqlash foydalanuvchi sozlamasiga bog‘liq.
- Foydalanuvchi tarixini o‘chirishi mumkin.
- Token tarqalib ketsa, BotFather’dagi `/revoke` orqali yangilang.
