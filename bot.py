import os
import re
import json
import hmac
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from aiohttp import web

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ---------------------------------------------------------------------------
# Logging & Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("aura_bot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
PORT = int(os.environ.get("PORT", "10000"))

FOUNDER_ACTION_EMAIL = os.environ.get("FOUNDER_ACTION_EMAIL", "")
FOUNDER_TELEGRAM_ID = os.environ.get("FOUNDER_TELEGRAM_ID", "")
SUPPORT_WEBHOOK_SECRET = os.environ.get("SUPPORT_WEBHOOK_SECRET", "")
UPI_GATEWAY_CHECKOUT_URL = os.environ.get("UPI_GATEWAY_CHECKOUT_URL", "https://example.com/upi")
SUPPORT_FORM_URLS = json.loads(os.environ.get("SUPPORT_FORM_URLS_JSON", "{}"))

IST = timezone(timedelta(hours=5, minutes=30))

# Conversation states
LANG, DOB, LOCATION, RASI = range(4)

# Header tuned so the divider starts under the first ॐ and ends under the second ॐ
CARD_HEADER = (
    "ॐ  <b>AURA</b>  |  Daily Morning Grace &amp; Divine Blessings  ॐ\n"
    "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
)

LANGUAGES = {
    "en": "English",
    "ta": "தமிழ் (Tamil)",
    "hi": "हिन्दी (Hindi)",
    "te": "తెలుగు (Telugu)",
    "kn": "ಕನ್ನಡ (Kannada)",
    "ml": "മലയാളം (Malayalam)",
}

RASIS = [
    ("mesham", "Mesham"),
    ("rishabam", "Rishabam"),
    ("mithunam", "Mithunam"),
    ("kadagam", "Kadagam"),
    ("simmam", "Simmam"),
    ("kanni", "Kanni"),
    ("thulam", "Thulam"),
    ("vrischikam", "Vrischikam"),
    ("dhanusu", "Dhanusu"),
    ("magaram", "Magaram"),
    ("kumbam", "Kumbam"),
    ("meenam", "Meenam"),
]

# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------
def get_db_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def ensure_subscribers_schema() -> None:
    """Auto-heals required columns on startup so Rasi save never fails on schema drift."""
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS subscribers (
            telegram_id BIGINT PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            preferred_language VARCHAR(8) DEFAULT 'en',
            dob VARCHAR(20),
            locality TEXT,
            city TEXT,
            rasi VARCHAR(32),
            frequency SMALLINT DEFAULT 1,
            is_active BOOLEAN DEFAULT TRUE,
            consent_given_at TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """,
        "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS first_name TEXT;",
        "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS username TEXT;",
        "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(8) DEFAULT 'en';",
        "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS dob VARCHAR(20);",
        "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS locality TEXT;",
        "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS city TEXT;",
        "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS rasi VARCHAR(32);",
        "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS frequency SMALLINT DEFAULT 1;",
        "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS consent_given_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",
        """
        CREATE TABLE IF NOT EXISTS daily_shared_cache (
            edition_date DATE NOT NULL,
            bucket_type VARCHAR(32) NOT NULL,
            bucket_key VARCHAR(128) NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (edition_date, bucket_type, bucket_key)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS message_ratings (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            edition_date DATE NOT NULL,
            rating SMALLINT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (telegram_id, edition_date)
        );
        """,
    ]
    try:
        with get_db_conn() as conn, conn.cursor() as cur:
            for stmt in ddl_statements:
                cur.execute(stmt)
            conn.commit()
        logger.info("Database schema verified successfully.")
    except Exception as exc:
        logger.exception("Schema verification failed: %s", exc)


def upsert_subscriber_profile(
    telegram_id: int,
    first_name: str,
    username: str,
    lang: str,
    dob: str,
    locality: str,
    rasi: str,
) -> None:
    city_part = locality.split(",")[-1].strip() if "," in locality else locality.strip()
    with get_db_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO subscribers (
                telegram_id, first_name, username, preferred_language,
                dob, locality, city, rasi, frequency, is_active,
                consent_given_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, TRUE, NOW(), NOW())
            ON CONFLICT (telegram_id) DO UPDATE SET
                first_name = EXCLUDED.first_name,
                username = EXCLUDED.username,
                preferred_language = EXCLUDED.preferred_language,
                dob = EXCLUDED.dob,
                locality = EXCLUDED.locality,
                city = EXCLUDED.city,
                rasi = EXCLUDED.rasi,
                frequency = 1,
                is_active = TRUE,
                updated_at = NOW();
            """,
            (telegram_id, first_name, username, lang, dob, locality, city_part, rasi),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Message Tracking & Cleanup Helpers (For Clean "Back" Navigation)
# ---------------------------------------------------------------------------
def track_onboarding_msg(context: ContextTypes.DEFAULT_TYPE, msg_id: Optional[int]) -> None:
    if not msg_id:
        return
    ids = context.user_data.setdefault("onboarding_msg_ids", [])
    if msg_id not in ids:
        ids.append(msg_id)


async def cleanup_previous_messages(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    keep_msg_id: Optional[int] = None,
) -> None:
    """Deletes earlier onboarding prompts and typed user inputs when going Back."""
    ids = context.user_data.get("onboarding_msg_ids", [])
    remaining = []
    for mid in ids:
        if keep_msg_id and mid == keep_msg_id:
            remaining.append(mid)
            continue
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            # Ignore if already deleted or restricted by client
            pass
    context.user_data["onboarding_msg_ids"] = remaining


# ---------------------------------------------------------------------------
# UI Builders
# ---------------------------------------------------------------------------
def build_language_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("English", callback_data="lang:en"),
            InlineKeyboardButton("தமிழ் (Tamil)", callback_data="lang:ta"),
        ],
        [
            InlineKeyboardButton("हिन्दी (Hindi)", callback_data="lang:hi"),
            InlineKeyboardButton("తెలుగు (Telugu)", callback_data="lang:te"),
        ],
        [
            InlineKeyboardButton("ಕನ್ನಡ (Kannada)", callback_data="lang:kn"),
            InlineKeyboardButton("മലയാളം (Malayalam)", callback_data="lang:ml"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def build_language_prompt_text() -> str:
    return (
        f"{CARD_HEADER}"
        "<b>Select</b> your <b>Preferred Language</b> to begin"
    )


def build_welcome_dob_text(first_name: str) -> str:
    safe_name = first_name or "Friend"
    return (
        f"{CARD_HEADER}"
        f"Namaskaram, <b>{safe_name}</b> 🙏\n\n"
        "Every morning at <b>04:30 AM IST</b>, receive one calm and divine "
        "message to start your day with <b>Ashirvad:</b>\n\n"
        "• 🪔 Daily Blessing + 🛕 Temple &amp; Occasion Alerts\n\n"
        "• ⏳ Auspicious Timing\n\n"
        "• ✨ WoW [Words of Wisdom]\n\n"
        "• 🟡 Gold &amp; ⚪ Silver Rates\n\n"
        "• 🌦 Weather [Plan Your Day]\n\n"
        "<b>Step 1 of 3</b> — Enter your Date of Birth (e.g., <code>15-08-1985</code>):"
    )


def build_location_step_text(lang_label: str, dob: str) -> str:
    return (
        f"{CARD_HEADER}"
        f"✓ <b>Language:</b> {lang_label}\n\n"
        f"✓ <b>Date of Birth:</b> {dob}\n\n"
        "<b>Step 2 of 3</b> — Enter your Locality &amp; City (or just your City):\n"
        "<i>Example: Ambattur, Chennai, Adyar, Chennai, or Chennai\n"
        "Why? Adding your locality gives sharper local weather &amp; rain updates.</i>"
    )


def build_rasi_step_text(lang_label: str, dob: str, locality: str) -> str:
    return (
        f"{CARD_HEADER}"
        f"✓ <b>Language:</b> {lang_label}\n\n"
        f"✓ <b>Date of Birth:</b> {dob}\n\n"
        f"✓ <b>Locality / City:</b> {locality}\n\n"
        "<b>Step 3 of 3</b> — Select your Zodiac / Rasi:"
    )


def build_rasi_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(RASIS), 3):
        rows.append(
            [
                InlineKeyboardButton(label, callback_data=f"rasi:{code}")
                for code, label in RASIS[i : i + 3]
            ]
        )
    rows.append([InlineKeyboardButton("← Back to Locality / City", callback_data="back:location")])
    return InlineKeyboardMarkup(rows)


def build_daily_action_keyboard(telegram_id: int, lang: str, edition_date: str) -> InlineKeyboardMarkup:
    support_base = SUPPORT_FORM_URLS.get(lang) or SUPPORT_FORM_URLS.get("en") or "https://forms.google.com"
    sep = "&" if "?" in support_base else "?"
    support_url = f"{support_base}{sep}uid={telegram_id}&lang={lang}"
    pay_url = f"{UPI_GATEWAY_CHECKOUT_URL}?uid={telegram_id}&ref={edition_date}"

    rows = [
        [
            InlineKeyboardButton(f"{i}⭐", callback_data=f"rate:{edition_date}:{i}")
            for i in range(1, 6)
        ],
        [
            InlineKeyboardButton("✨ Other Services", callback_data="menu:other_services"),
            InlineKeyboardButton("🙏 Support / Dakshina", url=pay_url),
        ],
        [
            InlineKeyboardButton("💬 Help & Feedback", url=support_url),
        ],
    ]
    if lang != "en":
        rows.append(
            [InlineKeyboardButton("🌐 Translate [ENG]", callback_data=f"translate:en:{edition_date}")]
        )
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Onboarding Handlers
# ---------------------------------------------------------------------------
async def start_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    await cleanup_previous_messages(context, chat_id)
    context.user_data.clear()

    if update.message:
        track_onboarding_msg(context, update.message.message_id)

    sent = await update.effective_message.reply_text(
        build_language_prompt_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=build_language_keyboard(),
    )
    track_onboarding_msg(context, sent.message_id)
    return LANG


async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    lang_code = query.data.split(":", 1)[1]
    context.user_data["lang"] = lang_code
    context.user_data["lang_label"] = LANGUAGES.get(lang_code, "English")

    first_name = update.effective_user.first_name if update.effective_user else "Friend"
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back to Language", callback_data="back:lang")]]
    )
    await query.edit_message_text(
        build_welcome_dob_text(first_name),
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    track_onboarding_msg(context, query.message.message_id)
    return DOB


async def set_dob_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    track_onboarding_msg(context, update.message.message_id)

    if not re.match(r"^\d{2}[-/]\d{2}[-/]\d{4}$", text):
        warn = await update.message.reply_text(
            f"{CARD_HEADER}Please enter a valid Date of Birth in <code>DD-MM-YYYY</code> format (e.g., <code>15-08-1985</code>):",
            parse_mode=ParseMode.HTML,
        )
        track_onboarding_msg(context, warn.message_id)
        return DOB

    dob_clean = text.replace("/", "-")
    context.user_data["dob"] = dob_clean
    lang_label = context.user_data.get("lang_label", "English")

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("← Back to Date of Birth", callback_data="back:dob")]]
    )
    sent = await update.message.reply_text(
        build_location_step_text(lang_label, dob_clean),
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    track_onboarding_msg(context, sent.message_id)
    return LOCATION


async def set_location_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    locality = (update.message.text or "").strip()
    track_onboarding_msg(context, update.message.message_id)

    if len(locality) < 2:
        warn = await update.message.reply_text(
            f"{CARD_HEADER}Please enter your Locality &amp; City (e.g., <code>Adyar, Chennai</code>):",
            parse_mode=ParseMode.HTML,
        )
        track_onboarding_msg(context, warn.message_id)
        return LOCATION

    context.user_data["locality"] = locality
    lang_label = context.user_data.get("lang_label", "English")
    dob = context.user_data.get("dob", "")

    sent = await update.message.reply_text(
        build_rasi_step_text(lang_label, dob, locality),
        parse_mode=ParseMode.HTML,
        reply_markup=build_rasi_keyboard(),
    )
    track_onboarding_msg(context, sent.message_id)
    return RASI


async def set_rasi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    try:
        rasi_code = query.data.split(":", 1)[1]
        rasi_label = dict(RASIS).get(rasi_code, rasi_code.title())

        user = update.effective_user
        telegram_id = user.id
        first_name = user.first_name or ""
        username = user.username or ""

        lang = context.user_data.get("lang", "en")
        lang_label = context.user_data.get("lang_label", LANGUAGES.get(lang, "English"))
        dob = context.user_data.get("dob", "Not set")
        locality = context.user_data.get("locality", "Chennai")

        upsert_subscriber_profile(
            telegram_id=telegram_id,
            first_name=first_name,
            username=username,
            lang=lang,
            dob=dob,
            locality=locality,
            rasi=rasi_code,
        )

        # Clean up earlier onboarding messages so only the final confirmation card remains
        await cleanup_previous_messages(
            context,
            chat_id=query.message.chat_id,
            keep_msg_id=query.message.message_id,
        )

        confirmation_text = (
            f"{CARD_HEADER}"
            "🙏 <b>Subscription Confirmed — Ashirvad Active</b>\n\n"
            f"✓ <b>Language:</b> {lang_label}\n"
            f"✓ <b>Date of Birth:</b> {dob}\n"
            f"✓ <b>Locality / City:</b> {locality}\n"
            f"✓ <b>Zodiac / Rasi:</b> {rasi_label}\n"
            "✓ <b>Daily Delivery:</b> 04:30 AM IST\n\n"
            "You can update preferences anytime with /start or erase your data with /delete_data."
        )
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("📨 Send Today's Card Now", callback_data="send_sample_now")],
                [InlineKeyboardButton("⚙️ Edit Preferences", callback_data="back:lang")],
            ]
        )
        await query.edit_message_text(
            confirmation_text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        context.user_data.pop("onboarding_msg_ids", None)
    except Exception as exc:
        logger.exception("Error in set_rasi_callback: %s", exc)
        await query.edit_message_text(
            f"{CARD_HEADER}"
            "⚠️ We hit a temporary snag saving your Rasi. Please tap /start to try again.",
            parse_mode=ParseMode.HTML,
        )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Back Navigation Handlers (With Previous Message Cleanup)
# ---------------------------------------------------------------------------
async def back_navigation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    target = query.data.split(":", 1)[1]
    chat_id = query.message.chat_id
    current_msg_id = query.message.message_id

    # Delete all earlier onboarding steps & user text messages above the active card
    await cleanup_previous_messages(context, chat_id=chat_id, keep_msg_id=current_msg_id)
    track_onboarding_msg(context, current_msg_id)

    if target == "lang":
        await query.edit_message_text(
            build_language_prompt_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=build_language_keyboard(),
        )
        return LANG

    if target == "dob":
        first_name = update.effective_user.first_name if update.effective_user else "Friend"
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("← Back to Language", callback_data="back:lang")]]
        )
        await query.edit_message_text(
            build_welcome_dob_text(first_name),
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return DOB

    if target == "location":
        lang_label = context.user_data.get("lang_label", "English")
        dob = context.user_data.get("dob", "")
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("← Back to Date of Birth", callback_data="back:dob")]]
        )
        await query.edit_message_text(
            build_location_step_text(lang_label, dob),
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return LOCATION

    return LANG


# ---------------------------------------------------------------------------
# Instant Sample Card, Rating, Translate & Data Erasure Handlers
# ---------------------------------------------------------------------------
async def send_sample_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Preparing today's divine blessing...")

    telegram_id = update.effective_user.id
    today_ist = datetime.now(IST).date()

    with get_db_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM subscribers WHERE telegram_id = %s;", (telegram_id,))
        sub = cur.fetchone()
        if not sub:
            await query.message.reply_text("Please complete /start setup first.")
            return

        lang = sub.get("preferred_language") or "en"
        rasi = sub.get("rasi") or "mesham"
        city = (sub.get("city") or "Chennai").lower()

        cur.execute(
            """
            SELECT bucket_type, bucket_key, payload
            FROM daily_shared_cache
            WHERE edition_date = %s;
            """,
            (today_ist,),
        )
        rows = cur.fetchall()

    cache = {(r["bucket_type"], r["bucket_key"]): r["payload"] for r in rows}
    deity_block = (cache.get(("DEITY_DAY", "TODAY")) or {}).get(lang) or (
        cache.get(("DEITY_DAY", "TODAY")) or {}
    ).get("en", "🪔 <b>Daily Blessing:</b> Om Namah Shivaya — May peace and clarity guide your day.")
    rasi_block = (cache.get(("RASI", rasi)) or {}).get(lang) or (
        cache.get(("RASI", rasi)) or {}
    ).get("en", "✨ <b>Rasi Guidance:</b> Stay steady, speak kindly, and focus on priority tasks.")
    ausp_block = (cache.get(("AUSPICIOUS", city)) or cache.get(("AUSPICIOUS", "chennai")) or {}).get(
        lang, "⏳ <b>Auspicious Timing:</b> Morning 06:00–07:30 AM"
    )
    gold_block = (cache.get(("GOLD_INR", "INDIA")) or {}).get(
        lang, f"🟡 Gold &amp; ⚪ Silver Rates [As of {today_ist.strftime('%d %b %Y')}]: Updating shortly"
    )
    weather_block = (cache.get(("WEATHER", city)) or cache.get(("WEATHER", "chennai")) or {}).get(
        lang, "🌦 <b>Weather:</b> Pleasant morning breeze"
    )
    quote_block = (cache.get(("QUOTE", "TODAY")) or {}).get(lang) or (
        cache.get(("QUOTE", "TODAY")) or {}
    ).get(
        "en",
        '✨ <b>WoW [Words of Wisdom]:</b>\n"You have a right to perform your prescribed duty, but never to its fruits." — <i>Bhagavad Gita (2.47)</i>',
    )

    message_text = (
        f"{CARD_HEADER}"
        f"{deity_block}\n\n"
        f"{rasi_block}\n\n"
        f"{ausp_block}\n\n"
        f"{gold_block}\n\n"
        f"{weather_block}\n\n"
        f"{quote_block}"
    )

    await query.message.reply_text(
        message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_daily_action_keyboard(telegram_id, lang, str(today_ist)),
    )


async def rating_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    _, edition_date, score_str = query.data.split(":")
    score = int(score_str)
    try:
        with get_db_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO message_ratings (telegram_id, edition_date, rating)
                VALUES (%s, %s, %s)
                ON CONFLICT (telegram_id, edition_date)
                DO UPDATE SET rating = EXCLUDED.rating;
                """,
                (update.effective_user.id, edition_date, score),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("Rating save skipped: %s", exc)
    await query.answer(f"Thank you for your {score}⭐ feedback!", show_alert=False)


async def translate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Loading English translation...")
    _, _, edition_date = query.data.split(":")
    telegram_id = update.effective_user.id

    with get_db_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM subscribers WHERE telegram_id = %s;", (telegram_id,))
        sub = cur.fetchone() or {}
        rasi = sub.get("rasi") or "mesham"
        city = (sub.get("city") or "chennai").lower()

        cur.execute(
            "SELECT bucket_type, bucket_key, payload FROM daily_shared_cache WHERE edition_date = %s;",
            (edition_date,),
        )
        rows = cur.fetchall()

    cache = {(r["bucket_type"], r["bucket_key"]): r["payload"] for r in rows}
    en_text = (
        f"{CARD_HEADER}"
        f"{(cache.get(('DEITY_DAY', 'TODAY')) or {}).get('en', '')}\n\n"
        f"{(cache.get(('RASI', rasi)) or {}).get('en', '')}\n\n"
        f"{(cache.get(('AUSPICIOUS', city)) or cache.get(('AUSPICIOUS', 'chennai')) or {}).get('en', '')}\n\n"
        f"{(cache.get(('GOLD_INR', 'INDIA')) or {}).get('en', '')}\n\n"
        f"{(cache.get(('WEATHER', city)) or cache.get(('WEATHER', 'chennai')) or {}).get('en', '')}\n\n"
        f"{(cache.get(('QUOTE', 'TODAY')) or {}).get('en', '')}"
    )
    await query.message.reply_text(en_text, parse_mode=ParseMode.HTML)


async def delete_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    with get_db_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM subscribers WHERE telegram_id = %s;", (telegram_id,))
        conn.commit()
    await update.message.reply_text(
        f"{CARD_HEADER}"
        "🗑️ Your profile and preferences have been permanently erased.\n"
        "You may re-subscribe anytime with /start.",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# Health Check & Webhook HTTP Server (Render)
# ---------------------------------------------------------------------------
async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "aura-telegram-bot"})


async def post_init(application: Application) -> None:
    ensure_subscribers_schema()


def build_application() -> Application:
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .read_timeout(60)
        .write_timeout(60)
        .connect_timeout(30)
        .post_init(post_init)
        .build()
    )

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start_onboarding)],
        states={
            LANG: [
                CallbackQueryHandler(set_language_callback, pattern=r"^lang:"),
            ],
            DOB: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_dob_message),
                CallbackQueryHandler(back_navigation_callback, pattern=r"^back:"),
            ],
            LOCATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_location_message),
                CallbackQueryHandler(back_navigation_callback, pattern=r"^back:"),
            ],
            RASI: [
                CallbackQueryHandler(set_rasi_callback, pattern=r"^rasi:"),
                CallbackQueryHandler(back_navigation_callback, pattern=r"^back:"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start_onboarding),
            CallbackQueryHandler(back_navigation_callback, pattern=r"^back:"),
            CallbackQueryHandler(set_rasi_callback, pattern=r"^rasi:"),
        ],
        per_message=False,
    )

    app.add_handler(conv)
    # Global fallbacks ensure buttons remain responsive even after a server restart
    app.add_handler(CallbackQueryHandler(set_language_callback, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(set_rasi_callback, pattern=r"^rasi:"))
    app.add_handler(CallbackQueryHandler(back_navigation_callback, pattern=r"^back:"))
    app.add_handler(CallbackQueryHandler(send_sample_card_callback, pattern=r"^send_sample_now$"))
    app.add_handler(CallbackQueryHandler(rating_callback, pattern=r"^rate:"))
    app.add_handler(CallbackQueryHandler(translate_callback, pattern=r"^translate:"))
    app.add_handler(CommandHandler("delete_data", delete_data_command))
    app.add_handler(CommandHandler("stop", delete_data_command))
    return app


async def main() -> None:
    application = build_application()
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)

    web_app = web.Application()
    web_app.router.add_get("/health", health_handler)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("AURA bot polling + health server active on port %s", PORT)

    # Keep running forever
    import asyncio
    await asyncio.Event().wait()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
