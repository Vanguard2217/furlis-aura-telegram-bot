# broadcast_daily.py — FURLIS AURA Daily Broadcaster with Auto File-ID Caching
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta
import aiohttp
import asyncpg

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
UPI_CHECKOUT_BASE_URL = os.environ["UPI_GATEWAY_CHECKOUT_URL"]
SUPPORT_FORM_URLS = json.loads(os.environ.get("SUPPORT_FORM_URLS_JSON", "{}"))
DEFAULT_SUPPORT_FORM_URL = os.environ.get("SUPPORT_FORM_URL", "")
IST = timezone(timedelta(hours=5, minutes=30))
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
BATCH_CONCURRENCY = 25

def build_support_url(telegram_id: int, lang: str) -> str:
    template = SUPPORT_FORM_URLS.get(lang) or SUPPORT_FORM_URLS.get("en") or DEFAULT_SUPPORT_FORM_URL
    if not template:
        return "https://t.me"
    if "{uid}" in template:
        return template.format(uid=telegram_id)
    sep = "&" if "?" in template else "?"
    return f"{template}{sep}uid={telegram_id}"

def build_inline_keyboard_dict(edition_date: str, telegram_id: int, lang: str) -> dict:
    upi_url = f"{UPI_CHECKOUT_BASE_URL}?uid={telegram_id}&ref={edition_date}"
    support_url = build_support_url(telegram_id, lang)
    rows = [
        [{"text": f"⭐ {i}", "callback_data": f"rate:{edition_date}:{i}"} for i in range(1, 6)],
        [{"text": "📰 Other Services (12 Pillars & Social)", "callback_data": "menu:other_services"}],
        [{"text": "💳 Pay (UPI)", "url": upi_url}],
        [{"text": "🛠️ Support (Suggestion / Complaint)", "url": support_url}],
    ]
    if lang != "en":
        rows.append([{"text": "🌐 Translate [ENG]", "callback_data": f"translate:en:{edition_date}"}])
    return {"inline_keyboard": rows}

def render_caption(deity: dict, gold: dict, rasi_name: str, rasi: dict, city_name: str, city: dict, quote_block: dict) -> str:
    text = (
        f"✨ FURLIS AURA ✨\n\n🙏 {deity.get('title', 'Daily Blessing')}\n{deity.get('slogan', '')}\n\n"
        f"🛕 {deity.get('occasion_temple', '')}\n🪙 Gold (22K): {gold.get('rate_22k', 'N/A')} | 24K: {gold.get('rate_24k', 'N/A')}\n"
        f"✨ {rasi_name}: {rasi.get('three_words', '')}\n⏰ {city.get('auspicious_time', '')}\n🌤️ {city_name}: {city.get('weather', '')}\n\n"
        f"💡 \"{quote_block.get('quote', '')}\" — {quote_block.get('author', '')}"
    )
    return text[:1020] + "..." if len(text) > 1024 else text

async def send_to_subscriber(session: aiohttp.ClientSession, pool: asyncpg.Pool, sub: asyncpg.Record, cache_map: dict, edition_date: str) -> bool:
    uid = sub["telegram_id"]
    lang = (sub["preferred_language"] or "en").lower()
    city_name = (sub["city"] or "Chennai").strip()
    rasi_name = (sub["rasi"] or "Mesham").strip()
    deity_key = "DEITY_ALL_OCCASIONS" if sub["deity_mode"] == "ALL_OCCASIONS" else "DEITY_DAY_OF_WEEK"

    def get_bucket(b_key: str) -> tuple[dict, str | None]:
        item = cache_map.get((lang, b_key)) or cache_map.get(("en", b_key))
        return (item["payload"], item["file_id"]) if item else ({}, None)

    deity, file_id = get_bucket(deity_key)
    gold, _ = get_bucket("GOLD_INR")
    rasi, _ = get_bucket(f"RASI_{rasi_name.upper()}")
    city, _ = get_bucket(f"CITY_{city_name.upper()}")
    if not city:
        city, _ = get_bucket("CITY_CHENNAI")
    quote_block, _ = get_bucket("FAMOUS_QUOTE")
    caption = render_caption(deity, gold, rasi_name, rasi, city_name, city, quote_block)
    reply_markup = build_inline_keyboard_dict(edition_date, uid, lang)
    asset_path = deity.get("asset_path", "")

    try:
        if file_id:
            resp = await session.post(f"{TELEGRAM_API_BASE}/sendPhoto", json={"chat_id": uid, "photo": file_id, "caption": caption, "reply_markup": reply_markup}, timeout=15)
        elif asset_path and Path(asset_path).is_file():
            form = aiohttp.FormData()
            form.add_field("chat_id", str(uid))
            form.add_field("caption", caption)
            form.add_field("reply_markup", json.dumps(reply_markup))
            form.add_field("photo", Path(asset_path).read_bytes(), filename=Path(asset_path).name, content_type="image/png")
            resp = await session.post(f"{TELEGRAM_API_BASE}/sendPhoto", data=form, timeout=30)
        else:
            resp = await session.post(f"{TELEGRAM_API_BASE}/sendMessage", json={"chat_id": uid, "text": caption, "reply_markup": reply_markup}, timeout=15)

        async with resp:
            if resp.status == 200:
                body = await resp.json()
                photos = body.get("result", {}).get("photo") or []
                if not file_id and photos:
                    new_file_id = photos[-1]["file_id"]
                    for k in [(lang, deity_key), ("en", deity_key)]:
                        if k in cache_map:
                            cache_map[k]["file_id"] = new_file_id
                    await pool.execute("UPDATE daily_shared_cache SET telegram_file_id = $1 WHERE edition_date = $2::date AND bucket_key = $3;", new_file_id, edition_date, deity_key)
                return True
            if resp.status == 403:
                await pool.execute("UPDATE subscribers SET is_active = FALSE, updated_at = NOW() WHERE telegram_id = $1;", uid)
            elif resp.status == 429:
                body = await resp.json()
                await asyncio.sleep(int(body.get("parameters", {}).get("retry_after", 3)))
    except Exception:
        pass
    return False

async def run_broadcast() -> None:
    edition_date = datetime.now(IST).strftime("%Y-%m-%d")
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    try:
        rows = await pool.fetch("SELECT language, bucket_key, payload_json, telegram_file_id FROM daily_shared_cache WHERE edition_date = $1::date;", edition_date)
        cache_map = {(r["language"], r["bucket_key"]): {"payload": json.loads(r["payload_json"]) if isinstance(r["payload_json"], str) else r["payload_json"], "file_id": r["telegram_file_id"]} for r in rows}
        subs = await pool.fetch("SELECT telegram_id, preferred_language, city, rasi, deity_mode FROM subscribers WHERE is_active = TRUE;")
        sent = 0
        async with aiohttp.ClientSession() as session:
            for i in range(0, len(subs), BATCH_CONCURRENCY):
                batch = subs[i : i + BATCH_CONCURRENCY]
                results = await asyncio.gather(*(send_to_subscriber(session, pool, s, cache_map, edition_date) for s in batch))
                sent += sum(1 for ok in results if ok)
                await asyncio.sleep(1.05)
        print(f"[{edition_date}] FURLIS AURA Broadcast complete: {sent}/{len(subs)} delivered.")
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(run_broadcast())
