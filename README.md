# QR Studio Telegram Bot

Aiogram 3 asosidagi, o‘zbek tilida ishlaydigan to‘liq QR kod generator bot. Menyular ataylab qisqa saqlangan: foydalanuvchi QR turini tanlaydi va faqat o‘sha tur uchun zarur savollarga javob beradi.

## Imkoniyatlar

- 11 tur: sayt, Wi‑Fi, telefon, matn, Telegram, email, SMS, WhatsApp, vCard kontakt, lokatsiya va taqvim tadbiri.
- Har bir maydon uchun tekshiruv va tushunarli xato xabari.
- 5 xil yuqori kontrastli dizayn; tayyor QR rangini bir bosishda almashtirish.
- PNG rasm va sifat yo‘qotmaydigan SVG fayl.
- SQLite tarix, sahifalash, qayta ochish, bittalab yoki to‘liq o‘chirish.
- Tarixni o‘chirish va Wi‑Fi parolini tarixga saqlamaslik uchun maxfiylik sozlamalari.
- Telegram lokatsiyasini to‘g‘ridan-to‘g‘ri qabul qilish.
- Flood himoyasi, foydalanuvchiga xavfsiz xato xabari va loglar.
- Admin uchun `/stats`.
- Docker, Docker Compose va oddiy Python orqali ishga tushirish.
- Asosiy validator va QR payloadlari uchun avtomatik testlar.

## 1. Bot tokenini olish

1. Telegram’da [@BotFather](https://t.me/BotFather) ni oching.
2. `/newbot` yuboring va bot nomi hamda username tanlang.
3. Berilgan tokenni nusxalang.
4. BotFather’da `/setdescription`, `/setabouttext` va `/setuserpic` orqali profilni to‘ldiring.

Tavsiya etiladigan description:

> Sayt, Wi‑Fi, telefon, kontakt va boshqa ma’lumotlar uchun tez va sifatli QR kod yarating.

## 2. Eng oson ishga tushirish — Docker

Serverda Docker va Docker Compose o‘rnatilgan bo‘lishi kerak.

```bash
cp .env.example .env
nano .env
docker compose up -d --build
docker compose logs -f
```

`.env` ichidagi `BOT_TOKEN` ni haqiqiy token bilan almashtiring. Ma’lumotlar `data/qrbot.sqlite3` faylida saqlanadi va konteyner yangilanganda yo‘qolmaydi.

To‘xtatish:

```bash
docker compose down
```

Yangilangan kodni ishga tushirish:

```bash
docker compose up -d --build
```

## 3. Oddiy Python orqali ishga tushirish

Python 3.11 yoki 3.12 tavsiya qilinadi.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python main.py
```

## Render Free Web Service

Repository’ni Render’ga ulang va quyidagilarni tanlang:

- Service type: **Web Service**
- Runtime: **Python 3**
- Build command: `pip install -r requirements.txt`
- Start command: `python main.py`
- Health check path: `/health`

Environment bo‘limida `BOT_TOKEN` va `ADMIN_IDS` qiymatlarini kiriting. Render avtomatik bergan `PORT` o‘zgaruvchisi orqali bot kichik health server ochadi; Telegram botning o‘zi polling rejimida ishlashda davom etadi.

Render Free fayl tizimi vaqtinchalik. Shu sabab bepul servis qayta ishga tushsa yoki deploy qilinsa, SQLite tarix yo‘qolishi mumkin. Doimiy tarix uchun pullik persistent disk yoki PostgreSQL kerak bo‘ladi.

Windows’da virtual muhitni faollashtirish:

```powershell
.venv\Scripts\activate
```

## Sozlamalar

| O‘zgaruvchi | Vazifasi | Standart |
|---|---|---|
| `BOT_TOKEN` | BotFather tokeni | Majburiy |
| `ADMIN_IDS` | `/stats` uchun Telegram IDlar | Bo‘sh |
| `DATABASE_PATH` | SQLite fayl manzili | `data/qrbot.sqlite3` |
| `LOG_LEVEL` | Log darajasi | `INFO` |

Telegram ID’ingizni [@userinfobot](https://t.me/userinfobot) orqali bilishingiz mumkin. Bir nechta admin ID vergul bilan yoziladi.

## Test va tekshiruv

Standart kutubxona bilan testlar:

```bash
python -m unittest discover -s tests -v
```

Development paketlari o‘rnatilgan bo‘lsa:

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

## Tuzilma

```text
app/
  bot.py          # ishga tushirish va Telegram buyruqlari
  handlers.py     # menyular, wizard va callbacklar
  payloads.py     # QR turlari va standart formatlar
  validators.py   # foydalanuvchi ma’lumotlarini tekshirish
  qr_builder.py   # PNG/SVG generator
  db.py           # SQLite qatlam
  keyboards.py    # inline/reply menyular
  config.py       # .env konfiguratsiya
tests/             # avtomatik testlar
```

## Maxfiylik

- Wi‑Fi QR kodi standart holatda tarixga saqlanmaydi.
- Foydalanuvchi barcha tarixni sozlamalardan o‘chirishi mumkin.
- Tarix o‘chiq QRlar faqat tugmalar ishlashi uchun vaqtincha saqlanadi va bot qayta ishga tushganda 24 soatdan eskilari tozalanadi.
- `.env` va SQLite bazasi Git’ga kiritilmaydi.
- Production serverda `data/` papkasiga faqat bot foydalanuvchisi kira olishini ta’minlang va muntazam zaxira nusxa oling.

## Muhim eslatma

Bot polling rejimida ishlaydi, shuning uchun domen yoki SSL sertifikat talab qilinmaydi. Tokenni hech qachon GitHub’ga yoki begona odamga yubormang. Token tarqalib ketsa, BotFather’dagi `/revoke` orqali darhol yangilang.
