import asyncio
import datetime
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import asyncpg
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("furlis_aura_broadcast")

IST = ZoneInfo("Asia/Kolkata")
DATABASE_URL = os.getenv("DATABASE_URL", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BROADCAST_CONCURRENCY = int(os.getenv("BROADCAST_CONCURRENCY", "15"))

CARD_LABELS: Dict[str, Dict[str, str]] = {
    "en": {
        "blessing": "Daily Blessing With",
        "temple": "Temple & Occasion Alerts",
        "rasi": "Daily Rasi",
        "timing": "Auspicious Timing",
        "gold": "Gold Rate",
        "silver": "Silver Rate",
        "weather": "Weather [Plan Your Day]",
        "wow": "WoW [Words of Wisdom]",
        "btn_profile": "👤 Profile",
        "btn_settings": "⚙️ Settings",
        "btn_translate": "🌐 Translate [ENG]",
        "back_card": "← Back",
    },
    "ta": {
        "blessing": "தினசரி ஆசீர்வாதம்",
        "temple": "கோவில் & விசேஷ அறிவிப்புகள்",
        "rasi": "தினசரி ராசி",
        "timing": "நல்ல நேரம்",
        "gold": "தங்கம் விலை",
        "silver": "வெள்ளி விலை",
        "weather": "வானிலை [உங்கள் நாளைத் திட்டமிடுங்கள்]",
        "wow": "WoW [ஞான மொழிகள்]",
        "btn_profile": "👤 சுயவிவரம்",
        "btn_settings": "⚙️ அமைப்புகள்",
        "btn_translate": "🌐 Translate [ENG]",
        "back_card": "← பின்செல்க",
    },
    "hi": {
        "blessing": "दैनिक आशीर्वाद",
        "temple": "मंदिर व विशेष पर्व अलर्ट",
        "rasi": "दैनिक राशि",
        "timing": "शुभ समय",
        "gold": "सोना भाव",
        "silver": "चांदी भाव",
        "weather": "मौसम [अपने दिन की योजना बनाएं]",
        "wow": "WoW [ज्ञान की बातें]",
        "btn_profile": "👤 प्रोफ़ाइल",
        "btn_settings": "⚙️ सेटिंग्स",
        "btn_translate": "🌐 Translate [ENG]",
        "back_card": "← वापस जाएं",
    },
    "te": {
        "blessing": "రోజువారీ ఆశీర్వాదం",
        "temple": "ఆలయ & ప్రత్యేక విశేషాలు",
        "rasi": "రోజువారీ రాశి",
        "timing": "శుభ సమయం",
        "gold": "బంగారం ధర",
        "silver": "వెండి ధర",
        "weather": "వాతావరణం [మీ రోజును ప్లాన్ చేసుకోండి]",
        "wow": "WoW [జ్ఞాన వాక్కులు]",
        "btn_profile": "👤 ప్రొఫైల్",
        "btn_settings": "⚙️ సెట్టింగ్స్",
        "btn_translate": "🌐 Translate [ENG]",
        "back_card": "← వెనుకకు",
    },
    "kn": {
        "blessing": "ದೈನಂದಿನ ಆಶೀರ್ವಾದ",
        "temple": "ದೇವಾಲಯ & ವಿಶೇಷ ಮಾಹಿತಿ",
        "rasi": "ದೈನಂದಿನ ರಾಶಿ",
        "timing": "ಶುಭ ಸಮಯ",
        "gold": "ಚಿನ್ನದ ದರ",
        "silver": "ಬೆಳ್ಳಿ ದರ",
        "weather": "ಹವಾಮಾನ [ನಿಮ್ಮ ದಿನವನ್ನು ಯೋಜಿಸಿ]",
        "wow": "WoW [ಜ್ಞಾನದ ಮಾತುಗಳು]",
        "btn_profile": "👤 ಪ್ರೊಫೈಲ್",
        "btn_settings": "⚙️ ಸೆಟ್ಟಿಂಗ್ಸ್",
        "btn_translate": "🌐 Translate [ENG]",
        "back_card": "← ಹಿಂದಕ್ಕೆ",
    },
    "ml": {
        "blessing": "ദൈനംദിന അനുഗ്രഹം",
        "temple": "ക്ഷേത്ര & വിശേഷ അറിയിപ്പുകളും",
        "rasi": "ദൈനംദിന രാശി",
        "timing": "ശുഭ സമయం",
        "gold": "സ്വർണ്ണ നിരക്ക്",
        "silver": "വെള്ളി നിരക്ക്",
        "weather": "കാലാവസ്ഥ [നിങ്ങളുടെ ദിവസം ആസൂത്രണം ചെയ്യുക]",
        "wow": "WoW [ജ്ഞാനവാക്കുകൾ]",
        "btn_profile": "👤 പ്രൊഫൈಲ್",
        "btn_settings": "⚙️ ക്രമീകരണങ്ങൾ",
        "btn_translate": "🌐 Translate [ENG]",
        "back_card": "← പിന്നിലേക്ക്",
    },
}


def get_labels(lang: Optional[str]) -> Dict[str, str]:
    code = (lang or "en").lower()
    return CARD_LABELS.get(code, CARD_LABELS["en"])


def build_inline_keyboard_dict(lang: Optional[str]) -> InlineKeyboardMarkup:
    lbl = get_labels(lang)
    toggle_lang = "en" if (lang or "en").lower() != "en" else "ta"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(lbl["btn_profile"], callback_data="panel:profile"),
                InlineKeyboardButton(lbl["btn_settings"], callback_data="panel:settings"),
            ],
            [
                InlineKeyboardButton(
                    lbl["btn_translate"], callback_data=f"translate:{toggle_lang}"
                ),
                InlineKeyboardButton(lbl["back_card"], callback_data="back:card"),
            ],
        ]
    )


async def load_cache_for_date(
    conn: asyncpg.Connection, edition_date: datetime.date
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT bucket_type, bucket_key, payload
        FROM daily_shared_cache
        WHERE edition_date = $1
        """,
        edition_date,
    )
    cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        raw = row["payload"]
        parsed = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        cache[(row["bucket_type"], row["bucket_key"])] = parsed
    return cache


def render_subscriber_card(
    sub: Dict[str, Any],
    cache: Dict[Tuple[str, str], Dict[str, Any]],
    edition_date: datetime.date,
) -> str:
    lang = (sub.get("preferred_language") or "en").lower()
    lbl = get_labels(lang)

    deity = cache.get(("DEITY_DAY", lang)) or cache.get(("DEITY_DAY", "en")) or {}
    rasi_key = (sub.get("rasi") or "MESHA").upper()
    rasi = (
        cache.get(("RASI", f"{rasi_key}:{lang}"))
        or cache.get(("RASI", f"{rasi_key}:en"))
        or {}
    )
    ausp = cache.get(("AUSPICIOUS", lang)) or cache.get(("AUSPICIOUS", "en")) or {}
    gold = cache.get(("GOLD_INR", "INR")) or cache.get(("GOLD_INR", lang)) or {}
    weather = (
        cache.get(("WEATHER", sub.get("city") or "CHENNAI"))
        or cache.get(("WEATHER", lang))
        or {}
    )
    quote = cache.get(("QUOTE", lang)) or cache.get(("QUOTE", "en")) or {}

    return "\n".join(
        [
            f"🕉 <b>FURLIS AURA</b> — <code>{edition_date.isoformat()}</code>",
            "",
            f"🪔 <b>{lbl['blessing']}</b>: {deity.get('blessing') or deity.get('title') or 'Daily Grace'}",
            f"🛕 <b>{lbl['temple']}</b>: {deity.get('occasion') or deity.get('temple') or 'Standard Observance'}",
            f"✨ <b>{lbl['rasi']} ({rasi_key})</b>: {rasi.get('summary') or 'Steady progress and clarity.'}",
            f"⏳ <b>{lbl['timing']}</b>: {ausp.get('window') or 'Morning & Evening IST'}",
            f"🟡 <b>{lbl['gold']}</b>: {gold.get('gold_22k') or gold.get('gold') or '—'} | ⚪️ <b>{lbl['silver']}</b>: {gold.get('silver') or '—'}",
            f"🌦 <b>{lbl['weather']}</b>: {weather.get('summary') or 'Clear skies'}",
            f"📜 <b>{lbl['wow']}</b>: {quote.get('text') or 'Walk with steady intention.'}",
        ]
    )


async def run_broadcast() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required.")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is required.")

    edition_date = datetime.datetime.now(IST).date()
    bot = Bot(token=BOT_TOKEN)
    pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=5)

    try:
        async with pool.acquire() as conn:
            cache = await load_cache_for_date(conn, edition_date)
            sub_rows: List[asyncpg.Record] = await conn.fetch(
                """
                SELECT telegram_id, preferred_language, city, rasi
                FROM subscribers
                """
            )

        subscribers = [dict(r) for r in sub_rows]
        sem = asyncio.Semaphore(BROADCAST_CONCURRENCY)

        async def _send_one(sub: Dict[str, Any]) -> None:
            async with sem:
                chat_id = int(sub["telegram_id"])
                lang = (sub.get("preferred_language") or "en").lower()
                text = render_subscriber_card(sub, cache, edition_date)
                kb = build_inline_keyboard_dict(lang)
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=kb,
                    )
                except Exception as exc:
                    logger.warning("Broadcast failed for %s: %s", chat_id, exc)

        await asyncio.gather(*(_send_one(s) for s in subscribers))
        logger.info(
            "Broadcast completed for %s across %d subscribers.",
            edition_date.isoformat(),
            len(subscribers),
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run_broadcast())
