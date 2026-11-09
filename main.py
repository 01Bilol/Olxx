#!/usr/bin/env python3
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")

CHECK_EVERY_SEC = 30
USD_RATE = 12800

MAX_PRICE_USD = {
    "11": 250, "12": 300, "13": 380, "14": 480,
    "15": 650, "16": 800, "17": 1000,
}
USE_PRICE_LIMIT = True

QUERIES = ["iphone", "айфон"]
CITY_ID = None
SEEN_FILE = "seen_ids.json"

API = "https://www.olx.uz/api/v1/offers/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

MODEL_RE = re.compile(
    r"(?:iphone|iphon|айфон|айфо)\s*[-]?\s*(1[1-7])\s*(pro\s*max|promax|pro|plus|air|mini)?",
    re.I,
)


def http_get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def tg(method, data):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    body = urllib.parse.urlencode(data).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=20) as r:
        return json.loads(r.read().decode())


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return None


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen)[-5000:], f)


def fetch_offers(query):
    params = {
        "offset": 0,
        "limit": 40,
        "query": query,
        "sort_by": "created_at:desc",
    }
    if CITY_ID:
        params["city_id"] = CITY_ID
    data = http_get(API + "?" + urllib.parse.urlencode(params))
    return data.get("data", [])


def get_price(offer):
    for p in offer.get("params", []):
        if p.get("key") == "price":
            v = p.get("value", {})
            val = v.get("value")
            cur = v.get("currency") or v.get("converted_currency")
            if val is not None:
                return float(val), cur
    return None, None


def price_usd(val, cur):
    if val is None:
        return None
    if cur and cur.upper() in ("UZS", "SUM", "СУМ"):
        return val / USD_RATE
    return val


def detect_model(offer):
    text = f"{offer.get('title', '')} {offer.get('description', '')}"
    m = MODEL_RE.search(text)
    if not m:
        return None, None
    num = m.group(1)
    suffix = (m.group(2) or "").lower().replace(" ", "")
    names = {"promax": "Pro Max", "pro": "Pro", "plus": "Plus",
             "air": "Air", "mini": "Mini", "": ""}
    return num, f"iPhone {num} {names.get(suffix, '')}".strip()


def notify(offer, model_name, val, cur, usd):
    price_txt = f"{int(val):,} {cur}".replace(",", " ") if val else "не указана"
    if usd and cur and cur.upper() != "USD":
        price_txt += f" (~${int(usd)})"
    loc = (offer.get("location") or {})
    place = ", ".join(x for x in [
        (loc.get("city") or {}).get("name"),
        (loc.get("district") or {}).get("name")] if x)
    caption = (
        f"📱 {model_name}\n"
        f"💰 {price_txt}\n"
        f"📍 {place}\n"
        f"🕒 {offer.get('created_time', '')[:16].replace('T', ' ')}\n"
        f"{offer.get('title', '')}\n"
        f"🔗 {offer.get('url')}"
    )
    photos = offer.get("photos") or []
    if photos:
        link = photos[0].get("link", "").replace("{width}", "800").replace("{height}", "600")
        try:
            tg("sendPhoto", {"chat_id": CHAT_ID, "photo": link, "caption": caption})
            return
        except Exception:
            pass
    tg("sendMessage", {"chat_id": CHAT_ID, "text": caption})


def main():
    seen = load_seen()
    first_run = seen is None
    seen = seen or set()
    print("Мониторинг запущен." + (" Первый запуск: запоминаю текущие объявления." if first_run else ""))

    while True:
        try:
            for q in QUERIES:
                for offer in fetch_offers(q):
                    oid = str(offer.get("id"))
                    if oid in seen:
                        continue
                    seen.add(oid)
                    if first_run:
                        continue
                    num, name = detect_model(offer)
                    if not num:
                        continue
                    val, cur = get_price(offer)
                    usd = price_usd(val, cur)
                    if USE_PRICE_LIMIT and usd is not None:
                        limit = MAX_PRICE_USD.get(num)
                        if limit and usd > limit:
                            continue
                    notify(offer, name, val, cur, usd)
                    print("Отправлено:", name, val, cur, offer.get("url"))
            if first_run:
                first_run = False
                print("Готово, жду новые объявления...")
            save_seen(seen)
        except Exception as e:
            print("Ошибка:", e)
        if "--once" in sys.argv:
            break
        time.sleep(CHECK_EVERY_SEC)


if __name__ == "__main__":
    main()
