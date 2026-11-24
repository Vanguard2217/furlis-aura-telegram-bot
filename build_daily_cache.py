# build_daily_cache.py — FURLIS AURA Daily Cache Builder
import os
import csv
import json
import asyncio
from io import StringIO
from datetime import datetime, timezone, timedelta
import aiohttp
import asyncpg

DATABASE_URL = os.environ["DATABASE_URL"]
GOOGLE_SHEET_CSV_BASE_URL = os.environ.get("GOOGLE_SHEET_CSV_BASE_URL", "")
IST = timezone(timedelta(hours=5, minutes=30))

CITY_COORDS = {
    "CHENNAI": {"name": "Chennai", "lat": 13.0827, "lon": 80.2707},
    "MUMBAI": {"name": "Mumbai", "lat": 19.0760, "lon": 72.8777},
    "BENGALURU": {"name": "Bengaluru", "lat": 12.9716, "lon": 77.5946},
    "DELHI": {"name": "Delhi", "lat": 28.6139, "lon": 77.2090},
    "HYDERABAD": {"name": "Hyderabad", "lat": 17.3850, "lon": 78.4867},
    "MADURAI": {"name": "Madurai", "lat": 9.9252, "lon": 78.1198},
    "COIMBATORE": {"name": "Coimbatore", "lat": 11.0168, "lon": 76.9558},
}
WEATHER_CODES = {
    0: "Clear Sky", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Foggy", 51: "Light Drizzle", 61: "Light Rain", 63: "Moderate Rain",
    80: "Rain Showers", 95: "Thunderstorm",
}
RAHUKALAM_SEGMENT = {0: 1, 1: 6, 2: 4, 3: 5, 4: 3, 5: 2, 6: 7}
NALLA_NERAM_SLOTS = {
    0: "06:15 AM – 07:15 AM | 04:45 PM – 05:45 PM",
    1: "07:45 AM – 08:45 AM | 04:45 PM – 05:45 PM",
    2: "09:15 AM – 10:15 AM | 04:45 PM – 05:45 PM",
    3: "10:45 AM – 11:45 AM | 04:45 PM – 05:45 PM",
    4: "09:15 AM – 10:15 AM | 04:45 PM – 05:45 PM",
    5: "09:15 AM – 10:15 AM | 04:45 PM – 05:45 PM",
    6: "07:45 AM – 08:45 AM | 04:45 PM – 05:45 PM",
}
DAY_DEITIES = {
    0: ("Monday Special — Lord Shiva Blessings", "May Lord Shiva’s grace bring inner stillness, clarity, and protection today.", "assets/deities/mon_shiva.png"),
    1: ("Tuesday Special — Lord Murugan & Hanuman Blessings", "May courage, focus, and strength remove every obstacle on your path.", "assets/deities/tue_murugan.png"),
    2: ("Wednesday Special — Lord Vinayagar & Perumal Blessings", "May Lord Vinayagar remove all obstacles and bring wisdom and steady progress today.", "assets/deities/wed_vinayagar.png"),
    3: ("Thursday Special — Sri Dakshinamoorthy & Guru Blessings", "May right knowledge, grace, and sound judgment illuminate your decisions.", "assets/deities/thu_guru.png"),
    4: ("Friday Special — Goddess Mahalakshmi & Amman Blessings", "May abundance, peace, and auspicious grace fill your household today.", "assets/deities/fri_amman.png"),
    5: ("Saturday Special — Lord Thirumal (Venkateswara) Blessings", "May Lord Thirumal’s grace bring clarity, peace, and steady strength today.", "assets/deities/sat_thirumal.png"),
    6: ("Sunday Special — Lord Surya Narayana Blessings", "May vitality, radiance, and positive energy empower your day.", "assets/deities/sun_surya.png"),
}
SCRIPTURE_QUOTES = [
    {"quote": "You have a right to perform your prescribed duty, but never to its fruits.", "author": "Bhagavad Gita (2.47)"},
    {"quote": "For him who has conquered the mind, the mind is the best of friends.", "author": "Bhagavad Gita (6.6)"},
    {"quote": "Arise, awake, and stop not till the goal is reached.", "author": "Katha Upanishad (1.3.14)"},
    {"quote": "Let noble thoughts come to us from every side.", "author": "Rigveda (1.89.1)"},
]
TROY_OUNCE_TO_GRAM = 31.1034768
INDIA_BULLION_PREMIUM_FACTOR = 1.065

async def fetch_sheet_tab_csv(session: aiohttp.ClientSession, tab_name: str) -> list[dict]:
    if not GOOGLE_SHEET_CSV_BASE_URL:
        return []
    url = f"{GOOGLE_SHEET_CSV_BASE_URL}&sheet={tab_name}" if "?" in GOOGLE_SHEET_CSV_BASE_URL else f"{GOOGLE_SHEET_CSV_BASE_URL}?sheet={tab_name}"
    try:
        async with session.get(url, timeout=12) as resp:
            if resp.status == 200:
                text = await resp.text()
                reader = csv.DictReader(StringIO(text))
                return list(reader)
    except Exception:
        pass
    return []

async def fetch_yahoo_price(session: aiohttp.ClientSession, symbol: str) -> float | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
    try:
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12) as resp:
            if resp.status == 200:
                data = await resp.json()
                return float(data["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception:
        pass
    return None

async def fetch_bullion_rates(session: aiohttp.ClientSession) -> dict:
    xau_usd, xag_usd, usd_inr = await asyncio.gather(
        fetch_yahoo_price(session, "XAUUSD=X"),
        fetch_yahoo_price(session, "XAGUSD=X"),
        fetch_yahoo_price(session, "INR=X"),
    )
    if xau_usd and usd_inr:
        rate_24k = round((xau_usd * usd_inr / TROY_OUNCE_TO_GRAM) * INDIA_BULLION_PREMIUM_FACTOR)
        rate_22k = round(rate_24k * 0.916)
        rate_18k = round(rate_24k * 0.750)
        silver_1g = round(((xag_usd or 31.0) * usd_inr / TROY_OUNCE_TO_GRAM) * INDIA_BULLION_PREMIUM_FACTOR, 1)
        return {
            "rate_22k": f"₹{rate_22k:,}/g", "rate_24k": f"₹{rate_24k:,}/g", "rate_18k": f"₹{rate_18k:,}/g",
            "rate_silver": f"₹{silver_1g}/g",
            "board_summary": f"22K (916): ₹{rate_22k:,}/g | 24K (999): ₹{rate_24k:,}/g | 18K: ₹{rate_18k:,}/g | Silver: ₹{silver_1g}/g (Indicative)",
        }
    return {"rate_22k": "Check showroom", "rate_24k": "Check showroom", "rate_18k": "Check showroom", "rate_silver": "Check showroom", "board_summary": "Indicative showroom rates"}

async def fetch_city_weather(session: aiohttp.ClientSession, lat: float, lon: float) -> str:
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code&timezone=Asia%2FKolkata"
    try:
        async with session.get(url, timeout=12) as resp:
            if resp.status == 200:
                cur = (await resp.json())["current"]
                return f"{round(cur['temperature_2m'])}°C, {WEATHER_CODES.get(int(cur['weather_code']), 'Pleasant')}, Humidity {round(cur['relative_humidity_2m'])}%"
    except Exception:
        pass
    return "29°C, Partly Cloudy"

async def fetch_auspicious_window(session: aiohttp.ClientSession, lat: float, lon: float, date_str: str, weekday: int) -> str:
    url = f"https://api.sunrise-sunset.org/json?lat={lat}&lng={lon}&date={date_str}&formatted=0"
    nalla = NALLA_NERAM_SLOTS[weekday]
    try:
        async with session.get(url, timeout=12) as resp:
            if resp.status == 200:
                res = (await resp.json())["results"]
                sr = datetime.fromisoformat(res["sunrise"]).astimezone(IST)
                ss = datetime.fromisoformat(res["sunset"]).astimezone(IST)
                seg = (ss - sr) / 8
                rk_idx = RAHUKALAM_SEGMENT[weekday]
                rk_start = (sr + seg * rk_idx).strftime("%I:%M %p")
                rk_end = (sr + seg * (rk_idx + 1)).strftime("%I:%M %p")
                return f"Nalla Neram: {nalla} | Rahukalam: {rk_start} – {rk_end}"
    except Exception:
        pass
    return f"Nalla Neram: {nalla}"

async def build_and_store_cache() -> None:
    now_ist = datetime.now(IST)
    edition_date = now_ist.strftime("%Y-%m-%d")
    weekday = now_ist.weekday()
    day_of_year = now_ist.timetuple().tm_yday
    deity_title, deity_slogan, asset_path = DAY_DEITIES[weekday]
    quote_item = SCRIPTURE_QUOTES[(day_of_year - 1) % len(SCRIPTURE_QUOTES)]
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    try:
        db_cities = await pool.fetch("SELECT DISTINCT UPPER(TRIM(city)) AS c FROM subscribers WHERE is_active = TRUE AND city IS NOT NULL;")
        active_city_keys = set(CITY_COORDS.keys()) | {r["c"] for r in db_cities if r["c"] in CITY_COORDS}
        async with aiohttp.ClientSession() as session:
            sheet_quotes = await fetch_sheet_tab_csv(session, "Quotes_Bank")
            if sheet_quotes:
                q_row = sheet_quotes[(day_of_year - 1) % len(sheet_quotes)]
                q_text = q_row.get("quote_en") or q_row.get("quote")
                q_auth = f"{q_row.get('scripture', '')} ({q_row.get('citation', '')})".strip() or q_row.get("author")
                if q_text and q_auth:
                    quote_item = {"quote": q_text, "author": q_auth}
            gold_data = await fetch_bullion_rates(session)
            city_payloads = {}
            for c_key in active_city_keys:
                meta = CITY_COORDS[c_key]
                weather_str, ausp_str = await asyncio.gather(
                    fetch_city_weather(session, meta["lat"], meta["lon"]),
                    fetch_auspicious_window(session, meta["lat"], meta["lon"], edition_date, weekday),
                )
                city_payloads[c_key] = {"weather": weather_str, "auspicious_time": ausp_str}
        buckets = [
            ("en", "DEITY_DAY_OF_WEEK", {"title": deity_title, "slogan": deity_slogan, "occasion_temple": "Daily Panchangam & local temple darshan observance.", "asset_path": asset_path}, None),
            ("en", "DEITY_ALL_OCCASIONS", {"title": deity_title, "slogan": deity_slogan, "occasion_temple": "Special Panchangam observance & temple highlights.", "asset_path": asset_path}, None),
            ("en", "GOLD_INR", gold_data, None),
            ("en", "FAMOUS_QUOTE", quote_item, None),
        ]
        for c_key, c_data in city_payloads.items():
            buckets.append(("en", f"CITY_{c_key}", c_data, None))
        for r in ["Mesham", "Rishabam", "Mithunam", "Kadagam", "Simmam", "Kanni", "Thulam", "Vrischikam", "Dhanusu", "Magaram", "Kumbam", "Meenam"]:
            buckets.append(("en", f"RASI_{r.upper()}", {"three_words": "Steady Focus • Helpful Partnership • Timely Resolution"}, None))
        for lang, bucket_key, payload, file_id in buckets:
            await pool.execute(
                """
                INSERT INTO daily_shared_cache (edition_date, language, bucket_key, payload_json, telegram_file_id)
                VALUES ($1::date, $2, $3, $4::jsonb, $5)
                ON CONFLICT (edition_date, language, bucket_key) DO UPDATE SET
                    payload_json = EXCLUDED.payload_json, telegram_file_id = COALESCE(EXCLUDED.telegram_file_id, daily_shared_cache.telegram_file_id);
                """,
                edition_date, lang, bucket_key, json.dumps(payload), file_id,
            )
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(build_and_store_cache())
