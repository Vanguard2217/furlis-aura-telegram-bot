import asyncio
import datetime
import json
import logging
import os
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import asyncpg
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("furlis_aura_bot")

IST = ZoneInfo("Asia/Kolkata")
DATABASE_URL = os.getenv("DATABASE_URL", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WELCOME_VIDEO_PATH = os.getenv(
    "WELCOME_VIDEO_PATH", "assets/welcome_aura_is_here_to_serve_6s.mp4"
)
WELCOME_VIDEO_WIDTH = int(os.getenv("WELCOME_VIDEO_WIDTH", "1280"))
WELCOME_VIDEO_HEIGHT = int(os.getenv("WELCOME_VIDEO_HEIGHT", "720"))

# Conversation states
CHOOSING_LANG, ENTERING_DOB, ENTERING_LOCATION, EDIT_VALUE = range(4)

SUPPORTED_LANGS = ("en", "ta", "hi", "te", "kn", "ml")

WELCOME_COPY: Dict[str, Dict[str, Any]] = {
    "en": {
        "greeting": "🙏 Welcome to <b>FURLIS AURA</b> — Your Daily Devotional & Telemetry Companion.",
        "bullets": [
            "• 🪔 Daily Blessing With 🛕 Temple &amp; Occasion Alerts",
            "• ✨ Daily Rasi &amp; Auspicious Timing (IST)",
            "• 🟡 Gold Rate ⚪️ Silver Rate",
            "• 🌦 Weather [Plan Your Day]",
            "• 📜 WoW [Words of Wisdom]",
        ],
        "prompt_lang": "Choose your preferred language:",
        "prompt_dob": "Enter your Date of Birth (DD/MM/YYYY):",
        "prompt_location": "Enter your City / Locality (e.g., Chennai, Mylapore):",
        "btn_profile": "👤 Profile",
        "btn_settings": "⚙️ Settings",
        "btn_other_services": "🧩 Other Services",
        "btn_12pillars": "🏛 12 Pillars View",
        "btn_translate": "🌐 Translate [ENG]",
        "btn_privacy": "🛡 Privacy & Data (DPDPA)",
        "btn_delete": "🗑 DELETE",
        "back_lang": "← Back",
        "back_dob": "← Back",
        "back_loc": "← Back",
        "back_card": "← Back",
        "back_profile": "← Back",
        "back_settings": "← Back",
        "send_now_btn": "📨 Send Today's Card Now",
        "card_error": "⚠️ We hit a temporary snag generating today's card. Please try again in a moment.",
    },
    "ta": {
        "greeting": "🙏 <b>FURLIS AURA</b>-க்கு வரவேற்கிறோம் — உங்கள் தினசரி ஆன்மீக மற்றும் தகவல் துணை.",
        "bullets": [
            "• 🪔 தினசரி ஆசீர்வாதம் மற்றும் 🛕 கோவில் &amp; விசேஷ அறிவிப்புகள்",
            "• ✨ தினசரி ராசி &amp; நல்ல நேரம் (IST)",
            "• 🟡 தங்கம் விலை ⚪️ வெள்ளி விலை",
            "• 🌦 வானிலை [உங்கள் நாளைத் திட்டமிடுங்கள்]",
            "• 📜 WoW [ஞான மொழிகள்]",
        ],
        "prompt_lang": "உங்கள் விருப்ப மொழியைத் தேர்ந்தெடுக்கவும்:",
        "prompt_dob": "உங்கள் பிறந்த தேதியை உள்ளிடவும் (DD/MM/YYYY):",
        "prompt_location": "உங்கள் நகரம் / பகுதியை உள்ளிடவும் (எ.கா., சென்னை, மயிலாப்பூர்):",
        "btn_profile": "👤 சுயவிவரம்",
        "btn_settings": "⚙️ அமைப்புகள்",
        "btn_other_services": "🧩 பிற சேவைகள்",
        "btn_12pillars": "🏛 12 தூண்கள் பார்வை",
        "btn_translate": "🌐 Translate [ENG]",
        "btn_privacy": "🛡 தனியுரிமை &amp; தரவு (DPDPA)",
        "btn_delete": "🗑 நீக்கு (DELETE)",
        "back_lang": "← பின்செல்க",
        "back_dob": "← பின்செல்க",
        "back_loc": "← பின்செல்க",
        "back_card": "← பின்செல்க",
        "back_profile": "← பின்செல்க",
        "back_settings": "← பின்செல்க",
        "send_now_btn": "📨 இன்றைய அட்டையை அனுப்பு",
        "card_error": "⚠️ இன்றைய அட்டையை உருவாக்குவதில் தற்காலிக சிக்கல் ஏற்பட்டது. சிறிது நேரத்தில் மீண்டும் முயற்சிக்கவும்.",
    },
    "hi": {
        "greeting": "🙏 <b>FURLIS AURA</b> में आपका स्वागत है — आपका दैनिक आध्यात्मिक एवं जानकारी साथी।",
        "bullets": [
            "• 🪔 दैनिक आशीर्वाद एवं 🛕 मंदिर व विशेष पर्व अलर्ट",
            "• ✨ दैनिक राशि एवं शुभ समय (IST)",
            "• 🟡 सोना भाव ⚪️ चांदी भाव",
            "• 🌦 मौसम [अपने दिन की योजना बनाएं]",
            "• 📜 WoW [ज्ञान की बातें]",
        ],
        "prompt_lang": "अपनी पसंदीदा भाषा चुनें:",
        "prompt_dob": "अपनी जन्म तिथि दर्ज करें (DD/MM/YYYY):",
        "prompt_location": "अपना शहर / क्षेत्र दर्ज करें (जैसे, चेन्नई, मैलापुर):",
        "btn_profile": "👤 प्रोफ़ाइल",
        "btn_settings": "⚙️ सेटिंग्स",
        "btn_other_services": "🧩 अन्य सेवाएं",
        "btn_12pillars": "🏛 12 स्तंभ दृश्य",
        "btn_translate": "🌐 Translate [ENG]",
        "btn_privacy": "🛡 गोपनीयता एवं डेटा (DPDPA)",
        "btn_delete": "🗑 हटाएं (DELETE)",
        "back_lang": "← वापस जाएं",
        "back_dob": "← वापस जाएं",
        "back_loc": "← वापस जाएं",
        "back_card": "← वापस जाएं",
        "back_profile": "← वापस जाएं",
        "back_settings": "← वापस जाएं",
        "send_now_btn": "📨 आज का कार्ड भेजें",
        "card_error": "⚠️ आज का कार्ड तैयार करने में अस्थायी समस्या आई है। कृपया थोड़ी देर बाद पुनः प्रयास करें।",
    },
    "te": {
        "greeting": "🙏 <b>FURLIS AURA</b> కు స్వాగతం — మీ రోజువారీ ఆధ్యాత్మిక &amp; సమాచార సహచరుడు.",
        "bullets": [
            "• 🪔 రోజువారీ ఆశీర్వాదం మరియు 🛕 ఆలయ &amp; ప్రత్యేక విశేషాలు",
            "• ✨ రోజువారీ రాశి &amp; శుభ సమయం (IST)",
            "• 🟡 బంగారం ధర ⚪️ వెండి ధర",
            "• 🌦 వాతావరణం [మీ రోజును ప్లాన్ చేసుకోండి]",
            "• 📜 WoW [జ్ఞాన వాక్కులు]",
        ],
        "prompt_lang": "మీకు ఇష్టమైన భాషను ఎంచుకోండి:",
        "prompt_dob": "మీ పుట్టిన తేదీని నమోదు చేయండి (DD/MM/YYYY):",
        "prompt_location": "మీ నగరం / ప్రాంతాన్ని నమోదు చేయండి (ఉదా., చెన్నై, మైలాపూర్):",
        "btn_profile": "👤 ప్రొఫైల్",
        "btn_settings": "⚙️ సెట్టింగ్స్",
        "btn_other_services": "🧩 ఇతర సేవలు",
        "btn_12pillars": "🏛 12 పిల్లర్స్ వ్యూ",
        "btn_translate": "🌐 Translate [ENG]",
        "btn_privacy": "🛡 గోప్యత &amp; డేటా (DPDPA)",
        "btn_delete": "🗑 తొలగించు (DELETE)",
        "back_lang": "← వెనుకకు",
        "back_dob": "← వెనుకకు",
        "back_loc": "← వెనుకకు",
        "back_card": "← వెనుకకు",
        "back_profile": "← వెనుకకు",
        "back_settings": "← వెనుకకు",
        "send_now_btn": "📨 నేటి కార్డ్ పంపండి",
        "card_error": "⚠️ నేటి కార్డ్ రూపొందించడంలో తాత్కాలిక అంతరాయం కలిగింది. దయచేసి కొద్దిసేపటి తర్వాత మళ్లీ ప్రయత్నించండి.",
    },
    "kn": {
        "greeting": "🙏 <b>FURLIS AURA</b> ಗೆ ಸುಸ್ವಾಗತ — ನಿಮ್ಮ ದೈನಂದಿನ ಆಧ್ಯಾತ್ಮಿಕ ಮತ್ತು ಮಾಹಿತಿ ಸಂಗಾತಿ.",
        "bullets": [
            "• 🪔 ದೈನಂದಿನ ಆಶೀರ್ವಾದ ಮತ್ತು 🛕 ದೇವಾಲಯ &amp; ವಿಶೇಷ ಮಾಹಿತಿ",
            "• ✨ ದೈನಂದಿನ ರಾಶಿ &amp; ಶುಭ ಸಮಯ (IST)",
            "• 🟡 ಚಿನ್ನದ ದರ ⚪️ ಬೆಳ್ಳಿ ದರ",
            "• 🌦 ಹವಾಮಾನ [ನಿಮ್ಮ ದಿನವನ್ನು ಯೋಜಿಸಿ]",
            "• 📜 WoW [ಜ್ಞಾನದ ಮಾತುಗಳು]",
        ],
        "prompt_lang": "ನಿಮ್ಮ ಆದ್ಯತೆಯ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ:",
        "prompt_dob": "ನಿಮ್ಮ ಜನ್ಮ ದಿನಾಂಕವನ್ನು ನಮೂದಿಸಿ (DD/MM/YYYY):",
        "prompt_location": "ನಿಮ್ಮ ನಗರ / ಪ್ರದೇಶವನ್ನು ನಮೂದಿಸಿ (ಉದಾ., ಚೆನ್ನೈ, ಮೈಲಾಪೋರ್):",
        "btn_profile": "👤 ಪ್ರೊಫೈಲ್",
        "btn_settings": "⚙️ ಸೆಟ್ಟಿಂಗ್ಸ್",
        "btn_other_services": "🧩 ಇತರ ಸೇವೆಗಳು",
        "btn_12pillars": "🏛 12 ಪಿಲ್ಲರ್ಸ್ ವೀಕ್ಷಣೆ",
        "btn_translate": "🌐 Translate [ENG]",
        "btn_privacy": "🛡 ಗೌಪ್ಯತೆ ಮತ್ತು ಡೇಟಾ (DPDPA)",
        "btn_delete": "🗑 ಅಳಿಸಿ (DELETE)",
        "back_lang": "← ಹಿಂದಕ್ಕೆ",
        "back_dob": "← ಹಿಂದಕ್ಕೆ",
        "back_loc": "← ಹಿಂದಕ್ಕೆ",
        "back_card": "← ಹಿಂದಕ್ಕೆ",
        "back_profile": "← ಹಿಂದಕ್ಕೆ",
        "back_settings": "← ಹಿಂದಕ್ಕೆ",
        "send_now_btn": "📨 ಇಂದಿನ ಕಾರ್ಡ್ ಕಳುಹಿಸಿ",
        "card_error": "⚠️ ಇಂದಿನ ಕಾರ್ಡ್ ಸಿದ್ಧಪಡಿಸುವಲ್ಲಿ ತಾತ್ಕಾಲಿಕ ತೊಂದರೆ ಎದುರಾಗಿದೆ. ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
    },
    "ml": {
        "greeting": "🙏 <b>FURLIS AURA</b>-യിലേക്ക് സ്വാഗതം — നിങ്ങളുടെ ദൈനംദിന ആത്മീയ &amp; വിവര കൂട്ടാളി.",
        "bullets": [
            "• 🪔 ദൈനംദിന അനുഗ്രഹവും 🛕 ക്ഷേത്ര &amp; വിശേഷ അറിയിപ്പുകളും",
            "• ✨ ദൈനംദിന രാശി &amp; ശുഭ സമയം (IST)",
            "• 🟡 സ്വർണ്ണ നിരക്ക് ⚪️ വെള്ളി നിരക്ക്",
            "• 🌦 കാലാവസ്ഥ [നിങ്ങളുടെ ദിവസം ആസൂത്രണം ചെയ്യുക]",
            "• 📜 WoW [ജ്ഞാനവാക്കുകൾ]",
        ],
        "prompt_lang": "നിങ്ങളുടെ ഇഷ്ടഭാഷ തിരഞ്ഞെടുക്കുക:",
        "prompt_dob": "ജനനത്തീയതി നൽകുക (DD/MM/YYYY):",
        "prompt_location": "നിങ്ങളുടെ നഗരം / പ്രദേശം നൽകുക (ഉദാ., ചെന്നൈ, മൈലാപ്പൂർ):",
        "btn_profile": "👤 പ്രൊഫൈൽ",
        "btn_settings": "⚙️ ക്രമീകരണങ്ങൾ",
        "btn_other_services": "🧩 മറ്റ് സേവനങ്ങൾ",
        "btn_12pillars": "🏛 12 പില്ലേഴ്സ് കാഴ്ച",
        "btn_translate": "🌐 Translate [ENG]",
        "btn_privacy": "🛡 സ്വകാര്യതയും ഡാറ്റയും (DPDPA)",
        "btn_delete": "🗑 നീക്കം ചെയ്യുക (DELETE)",
        "back_lang": "← പിന്നിലേക്ക്",
        "back_dob": "← പിന്നിലേക്ക്",
        "back_loc": "← പിന്നിലേക്ക്",
        "back_card": "← പിന്നിലേക്ക്",
        "back_profile": "← പിന്നിലേക്ക്",
        "back_settings": "← പിന്നിലേക്ക്",
        "send_now_btn": "📨 ഇന്നത്തെ കാർഡ് അയയ്ക്കുക",
        "card_error": "⚠️ ഇന്നത്തെ കാർഡ് തയ്യാറാക്കുന്നതിൽ താൽക്കാലിക തടസ്സം നേരിട്ടു. ദയവായി അൽപ്പസമയത്തിനകം വീണ്ടും ശ്രമിക്കുക.",
    },
}


def get_copy(lang: Optional[str]) -> Dict[str, Any]:
    code = (lang or "en").lower()
    return WELCOME_COPY.get(code, WELCOME_COPY["en"])


def today_ist_date() -> datetime.date:
    return datetime.datetime.now(IST).date()


async def get_db_pool(context: ContextTypes.DEFAULT_TYPE) -> asyncpg.Pool:
    pool = context.application.bot_data.get("db_pool")
    if pool is None:
        pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=10)
        context.application.bot_data["db_pool"] = pool
    return pool


async def ensure_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                telegram_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                preferred_language VARCHAR(8) DEFAULT 'en',
                dob VARCHAR(20),
                locality TEXT,
                city TEXT,
                state TEXT,
                country TEXT,
                rasi TEXT,
                pillars_12_enabled BOOLEAN DEFAULT FALSE,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
        await conn.execute(
            """
            ALTER TABLE subscribers
                ADD COLUMN IF NOT EXISTS username TEXT,
                ADD COLUMN IF NOT EXISTS dob VARCHAR(20),
                ADD COLUMN IF NOT EXISTS locality TEXT,
                ADD COLUMN IF NOT EXISTS pillars_12_enabled BOOLEAN DEFAULT FALSE;
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_shared_cache (
                edition_date DATE NOT NULL,
                bucket_type VARCHAR(32) NOT NULL,
                bucket_key VARCHAR(128) NOT NULL,
                payload JSONB NOT NULL,
                telegram_file_id TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (edition_date, bucket_type, bucket_key)
            );
            """
        )


async def fetch_subscriber(pool: asyncpg.Pool, telegram_id: int) -> Dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT telegram_id, username, first_name, preferred_language,
                   dob, locality, city, state, country, rasi, pillars_12_enabled
            FROM subscribers
            WHERE telegram_id = $1
            """,
            telegram_id,
        )
    if row:
        return dict(row)
    return {
        "telegram_id": telegram_id,
        "username": None,
        "first_name": "",
        "preferred_language": "en",
        "dob": None,
        "locality": None,
        "city": None,
        "state": None,
        "country": None,
        "rasi": None,
        "pillars_12_enabled": False,
    }


async def upsert_subscriber(pool: asyncpg.Pool, telegram_id: int, **fields: Any) -> None:
    allowed = {
        "username",
        "first_name",
        "preferred_language",
        "dob",
        "locality",
        "city",
        "state",
        "country",
        "rasi",
        "pillars_12_enabled",
    }
    clean_fields = {k: v for k, v in fields.items() if k in allowed}
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO subscribers (telegram_id, username, first_name, preferred_language, dob, locality)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (telegram_id) DO NOTHING
            """,
            telegram_id,
            clean_fields.get("username"),
            clean_fields.get("first_name"),
            clean_fields.get("preferred_language", "en"),
            clean_fields.get("dob"),
            clean_fields.get("locality"),
        )
        for col, val in clean_fields.items():
            await conn.execute(
                f"UPDATE subscribers SET {col} = $1, updated_at = NOW() WHERE telegram_id = $2",
                val,
                telegram_id,
            )


async def load_daily_buckets(
    pool: asyncpg.Pool, edition_date: datetime.date
) -> Dict[Tuple[str, str], Dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT bucket_type, bucket_key, payload
            FROM daily_shared_cache
            WHERE edition_date = $1
            """,
            edition_date,
        )
    buckets: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in rows:
        raw_payload = r["payload"]
        if isinstance(raw_payload, str):
            parsed = json.loads(raw_payload)
        else:
            parsed = dict(raw_payload or {})
        buckets[(r["bucket_type"], r["bucket_key"])] = parsed
    return buckets


def format_daily_card_text(
    sub: Dict[str, Any],
    buckets: Dict[Tuple[str, str], Dict[str, Any]],
    override_lang: Optional[str] = None,
) -> str:
    lang = (override_lang or sub.get("preferred_language") or "en").lower()
    cp = get_copy(lang)
    edition = today_ist_date().isoformat()

    deity = buckets.get(("DEITY_DAY", lang)) or buckets.get(("DEITY_DAY", "en")) or {}
    rasi_key = (sub.get("rasi") or "MESHA").upper()
    rasi = (
        buckets.get(("RASI", f"{rasi_key}:{lang}"))
        or buckets.get(("RASI", f"{rasi_key}:en"))
        or {}
    )
    ausp = buckets.get(("AUSPICIOUS", lang)) or buckets.get(("AUSPICIOUS", "en")) or {}
    gold = buckets.get(("GOLD_INR", "INR")) or buckets.get(("GOLD_INR", lang)) or {}
    weather = (
        buckets.get(("WEATHER", sub.get("city") or "CHENNAI"))
        or buckets.get(("WEATHER", lang))
        or {}
    )
    quote = buckets.get(("QUOTE", lang)) or buckets.get(("QUOTE", "en")) or {}

    lines = [
        f"🕉 <b>FURLIS AURA</b> — <code>{edition}</code> ({lang.upper()})",
        "",
        f"🪔 <b>Daily Blessing With</b>: {deity.get('blessing') or deity.get('title') or 'Daily Grace'}",
        f"🛕 <b>Temple &amp; Occasion Alerts</b>: {deity.get('occasion') or deity.get('temple') or 'Standard Observance'}",
        f"✨ <b>Rasi ({rasi_key})</b>: {rasi.get('summary') or 'Steady progress and clarity.'}",
        f"⏳ <b>Auspicious Timing</b>: {ausp.get('window') or 'Morning & Evening IST'}",
        f"🟡 <b>Gold Rate</b>: {gold.get('gold_22k') or gold.get('gold') or '—'} | ⚪️ <b>Silver Rate</b>: {gold.get('silver') or '—'}",
        f"🌦 <b>Weather</b>: {weather.get('summary') or 'Clear skies'}",
        f"📜 <b>WoW</b>: {quote.get('text') or 'Walk with steady intention.'}",
    ]
    if sub.get("pillars_12_enabled"):
        lines.append("🏛 <i>12 Pillars View: Active</i>")
    return "\n".join(lines)


def build_daily_action_keyboard(lang: Optional[str], current_lang: str) -> InlineKeyboardMarkup:
    cp = get_copy(lang)
    toggle_lang = "en" if current_lang != "en" else "ta"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(cp["btn_profile"], callback_data="panel:profile"),
                InlineKeyboardButton(cp["btn_settings"], callback_data="panel:settings"),
            ],
            [
                InlineKeyboardButton(cp["btn_other_services"], callback_data="panel:other_services"),
                InlineKeyboardButton(cp["btn_12pillars"], callback_data="panel:12pillars_toggle"),
            ],
            [
                InlineKeyboardButton(
                    cp["btn_translate"], callback_data=f"translate:{toggle_lang}"
                ),
                InlineKeyboardButton(cp["back_card"], callback_data="back:card"),
            ],
        ]
    )


async def send_welcome_video_top(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int
) -> None:
    if not WELCOME_VIDEO_PATH or not os.path.exists(WELCOME_VIDEO_PATH):
        return
    try:
        with open(WELCOME_VIDEO_PATH, "rb") as vf:
            await context.bot.send_video(
                chat_id=chat_id,
                video=vf,
                width=WELCOME_VIDEO_WIDTH,
                height=WELCOME_VIDEO_HEIGHT,
                supports_streaming=True,
            )
    except Exception as exc:
        logger.warning("Failed sending welcome video: %s", exc)


async def safe_render_view(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    prefer_new_message: bool = False,
) -> None:
    query = update.callback_query
    if query and query.message and not prefer_new_message:
        msg = query.message
        has_photo = bool(getattr(msg, "photo", None)) or bool(getattr(msg, "video", None))
        try:
            if has_photo:
                await msg.delete()
                await context.bot.send_message(
                    chat_id=msg.chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                )
            else:
                await query.edit_message_text(
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                )
            return
        except BadRequest as exc:
            logger.debug("Falling back to send_message after edit BadRequest: %s", exc)

    chat_id = update.effective_chat.id if update.effective_chat else None
    if chat_id:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    pool = await get_db_pool(context)
    await ensure_schema(pool)
    await upsert_subscriber(
        pool,
        user.id,
        username=user.username,
        first_name=user.first_name,
    )
    sub = await fetch_subscriber(pool, user.id)
    cp = get_copy(sub.get("preferred_language"))

    await send_welcome_video_top(context, update.effective_chat.id)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("English", callback_data="lang:en"),
                InlineKeyboardButton("தமிழ்", callback_data="lang:ta"),
                InlineKeyboardButton("हिन्दी", callback_data="lang:hi"),
            ],
            [
                InlineKeyboardButton("తెలుగు", callback_data="lang:te"),
                InlineKeyboardButton("ಕನ್ನಡ", callback_data="lang:kn"),
                InlineKeyboardButton("മലയാളം", callback_data="lang:ml"),
            ],
            [InlineKeyboardButton(cp["send_now_btn"], callback_data="send_sample_now")],
        ]
    )
    body = "\n".join([cp["greeting"], "", *cp["bullets"], "", cp["prompt_lang"]])
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=body,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )
    return CHOOSING_LANG


async def on_lang_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":", 1)[1]
    if lang not in SUPPORTED_LANGS:
        lang = "en"

    pool = await get_db_pool(context)
    await upsert_subscriber(pool, query.from_user.id, preferred_language=lang)
    cp = get_copy(lang)

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(cp["back_lang"], callback_data="back:lang")]]
    )
    await safe_render_view(update, context, cp["prompt_dob"], reply_markup=kb)
    return ENTERING_DOB


async def on_dob_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    dob_text = (update.message.text or "").strip()
    user = update.effective_user
    pool = await get_db_pool(context)
    await upsert_subscriber(pool, user.id, dob=dob_text)
    sub = await fetch_subscriber(pool, user.id)
    cp = get_copy(sub.get("preferred_language"))

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(cp["back_dob"], callback_data="back:dob")]]
    )
    await update.message.reply_text(
        cp["prompt_location"], parse_mode=ParseMode.HTML, reply_markup=kb
    )
    return ENTERING_LOCATION


async def on_location_entered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    loc_text = (update.message.text or "").strip()
    user = update.effective_user
    pool = await get_db_pool(context)
    city_part = loc_text.split(",")[0].strip() if loc_text else None
    await upsert_subscriber(pool, user.id, locality=loc_text, city=city_part)
    sub = await fetch_subscriber(pool, user.id)
    lang = (sub.get("preferred_language") or "en").lower()

    buckets = await load_daily_buckets(pool, today_ist_date())
    card_text = format_daily_card_text(sub, buckets, override_lang=lang)
    kb = build_daily_action_keyboard(lang, lang)
    await update.message.reply_text(card_text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return ConversationHandler.END


async def send_sample_card_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except BadRequest:
            pass

    user = update.effective_user
    try:
        pool = await get_db_pool(context)
        await ensure_schema(pool)
        sub = await fetch_subscriber(pool, user.id)
        lang = (sub.get("preferred_language") or "en").lower()
        buckets = await load_daily_buckets(pool, today_ist_date())
        card_text = format_daily_card_text(sub, buckets, override_lang=lang)
        kb = build_daily_action_keyboard(lang, lang)
        await safe_render_view(update, context, card_text, reply_markup=kb)
    except Exception as exc:
        logger.exception("send_sample_card_callback failed: %s", exc)
        sub_lang = "en"
        try:
            pool = await get_db_pool(context)
            sub = await fetch_subscriber(pool, user.id)
            sub_lang = (sub.get("preferred_language") or "en").lower()
        except Exception:
            pass
        cp = get_copy(sub_lang)
        await safe_render_view(update, context, cp["card_error"])


async def on_panel_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    _, action = query.data.split(":", 1)
    user_id = query.from_user.id
    pool = await get_db_pool(context)
    await ensure_schema(pool)
    sub = await fetch_subscriber(pool, user_id)
    lang = (sub.get("preferred_language") or "en").lower()
    cp = get_copy(lang)

    if action == "profile":
        text = (
            f"<b>{cp['btn_profile']}</b>\n"
            f"• ID: <code>{user_id}</code>\n"
            f"• DOB: <code>{sub.get('dob') or '—'}</code>\n"
            f"• Locality: <code>{sub.get('locality') or sub.get('city') or '—'}</code>\n"
            f"• Language: <code>{lang.upper()}</code>"
        )
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(cp["btn_settings"], callback_data="panel:settings")],
                [InlineKeyboardButton(cp["back_profile"], callback_data="back:profile")],
            ]
        )
        await safe_render_view(update, context, text, reply_markup=kb)

    elif action == "settings":
        text = (
            f"<b>{cp['btn_settings']}</b>\n"
            f"• Language: <code>{lang.upper()}</code>\n"
            f"• 12 Pillars View: <code>{'ON' if sub.get('pillars_12_enabled') else 'OFF'}</code>"
        )
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(cp["btn_privacy"], callback_data="panel:privacy"),
                    InlineKeyboardButton(cp["btn_delete"], callback_data="panel:delete_confirm"),
                ],
                [InlineKeyboardButton(cp["back_settings"], callback_data="back:settings")],
            ]
        )
        await safe_render_view(update, context, text, reply_markup=kb)

    elif action == "other_services":
        text = f"<b>{cp['btn_other_services']}</b>\n• Daily Panchang &amp; Telemetry"
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(cp["btn_12pillars"], callback_data="panel:12pillars_toggle")],
                [InlineKeyboardButton(cp["back_card"], callback_data="back:card")],
            ]
        )
        await safe_render_view(update, context, text, reply_markup=kb)

    elif action == "12pillars_toggle":
        new_val = not bool(sub.get("pillars_12_enabled"))
        await upsert_subscriber(pool, user_id, pillars_12_enabled=new_val)
        sub["pillars_12_enabled"] = new_val
        buckets = await load_daily_buckets(pool, today_ist_date())
        card_text = format_daily_card_text(sub, buckets, override_lang=lang)
        kb = build_daily_action_keyboard(lang, lang)
        await safe_render_view(update, context, card_text, reply_markup=kb)

    elif action == "privacy":
        text = f"<b>{cp['btn_privacy']}</b>\nDPDPA 2023 consent &amp; profile preferences active."
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(cp["back_settings"], callback_data="back:settings")]]
        )
        await safe_render_view(update, context, text, reply_markup=kb)

    elif action == "delete_confirm":
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM subscribers WHERE telegram_id = $1", user_id)
        await safe_render_view(update, context, f"{cp['btn_delete']} — Done.")


async def on_translate_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if not query:
        return
    try:
        await query.answer()
    except BadRequest:
        pass

    target_lang = query.data.split(":", 1)[1].lower()
    if target_lang not in SUPPORTED_LANGS:
        target_lang = "en"

    pool = await get_db_pool(context)
    sub = await fetch_subscriber(pool, query.from_user.id)
    buckets = await load_daily_buckets(pool, today_ist_date())
    card_text = format_daily_card_text(sub, buckets, override_lang=target_lang)
    kb = build_daily_action_keyboard(target_lang, target_lang)
    await safe_render_view(update, context, card_text, reply_markup=kb)


async def on_back_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    try:
        await query.answer()
    except BadRequest:
        pass

    target = query.data.split(":", 1)[1]
    pool = await get_db_pool(context)
    sub = await fetch_subscriber(pool, query.from_user.id)
    lang = (sub.get("preferred_language") or "en").lower()
    cp = get_copy(lang)

    if target in ("lang", "dob", "location"):
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("English", callback_data="lang:en"),
                    InlineKeyboardButton("தமிழ்", callback_data="lang:ta"),
                    InlineKeyboardButton("हिन्दी", callback_data="lang:hi"),
                ],
                [
                    InlineKeyboardButton("తెలుగు", callback_data="lang:te"),
                    InlineKeyboardButton("ಕನ್ನಡ", callback_data="lang:kn"),
                    InlineKeyboardButton("മലയാളം", callback_data="lang:ml"),
                ],
            ]
        )
        await safe_render_view(
            update, context, f"{cp['greeting']}\n\n{cp['prompt_lang']}", reply_markup=kb
        )
        return CHOOSING_LANG

    if target == "profile":
        await on_panel_action(
            Update(update.update_id, callback_query=query), context
        )
        return ConversationHandler.END

    # Default back:card or back:settings -> render today's card safely
    await send_sample_card_callback(update, context)
    return ConversationHandler.END


async def on_edit_value_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if update.callback_query and (update.callback_query.data or "").startswith("back:"):
        return await on_back_callback(update, context)
    return ConversationHandler.END


def build_application() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            CHOOSING_LANG: [
                CallbackQueryHandler(on_lang_chosen, pattern=r"^lang:[a-z]{2}$"),
                CallbackQueryHandler(send_sample_card_callback, pattern=r"^send_sample_now$"),
                CallbackQueryHandler(on_back_callback, pattern=r"^back:"),
            ],
            ENTERING_DOB: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_dob_entered),
                CallbackQueryHandler(on_back_callback, pattern=r"^back:"),
            ],
            ENTERING_LOCATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_location_entered),
                CallbackQueryHandler(on_back_callback, pattern=r"^back:"),
            ],
            EDIT_VALUE: [
                CallbackQueryHandler(on_back_callback, pattern=r"^back:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_edit_value_message),
            ],
        },
        fallbacks=[
            CommandHandler("start", cmd_start),
            CallbackQueryHandler(on_back_callback, pattern=r"^back:"),
        ],
        per_message=False,
    )

    app.add_handler(conv_handler)
    app.add_handler(
        CallbackQueryHandler(send_sample_card_callback, pattern=r"^send_sample_now$")
    )
    app.add_handler(
        CallbackQueryHandler(
            on_panel_action,
            pattern=r"^(panel|menu):(profile|settings|other_services|12pillars_toggle|privacy|delete_confirm)$",
        )
    )
    app.add_handler(
        CallbackQueryHandler(on_translate_callback, pattern=r"^translate:[a-z]{2}$")
    )
    app.add_handler(CallbackQueryHandler(on_back_callback, pattern=r"^back:"))
    return app


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required.")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is required.")
    app = build_application()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
