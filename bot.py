# bot.py — FURLIS AURA Telegram Bot Web Service
import os
import html
import uuid
import json
import asyncio
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone
import asyncpg
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes,
)

FEATURE_FREQUENCY_ACTIVE = False  # Default 1x/day; 2x/day parked for future rollout

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
FOUNDER_EMAIL = os.environ["FOUNDER_ACTION_EMAIL"]
FOUNDER_TELEGRAM_ID = int(os.environ.get("FOUNDER_TELEGRAM_ID", "0"))
SUPPORT_WEBHOOK_SECRET = os.environ["SUPPORT_WEBHOOK_SECRET"]
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ["SMTP_USER"]
SMTP_PASS = os.environ["SMTP_APP_PASSWORD"]
UPI_CHECKOUT_BASE_URL = os.environ["UPI_GATEWAY_CHECKOUT_URL"]
PORT = int(os.environ.get("PORT", "10000"))
SUPPORT_FORM_URLS = json.loads(os.environ.get("SUPPORT_FORM_URLS_JSON", "{}"))
DEFAULT_SUPPORT_FORM_URL = os.environ.get("SUPPORT_FORM_URL", "")
WELCOME_MEDIA_ID = os.environ.get("WELCOME_MEDIA_ID", "").strip()

SHORT_DISCLAIMER = (
    "⚖️ <i>Disclaimer: Devotional, astrology, gold/market, weather &amp; alert info is for general "
    "guidance only—not financial, medical, travel, or safety advice. Verify critical decisions independently.</i>"
)

db_pool: asyncpg.Pool | None = None
LANG, LOCATION, RASI = range(3)

LANG_NAMES = {
    "en": "English", "ta": "தமிழ் (Tamil)", "hi": "हिन्दी (Hindi)",
    "te": "తెలుగు (Telugu)", "kn": "ಕನ್ನಡ (Kannada)", "ml": "മലയാളം (Malayalam)"
}
RASI_LIST = [
    "Mesham", "Rishabam", "Mithunam", "Kadagam",
    "Simmam", "Kanni", "Thulam", "Vrischikam",
    "Dhanusu", "Magaram", "Kumbam", "Meenam"
]

def build_devotional_block(cache: dict) -> str:
    deity = cache.get("DEITY_DAY_OF_WEEK") or {}
    title = html.escape(str(deity.get("title") or "Daily Morning Blessing"))
    slogan = html.escape(str(deity.get("slogan") or "May peace, clarity, and auspicious grace guide your day."))
    lines = [f"🪔 <b>{title}</b>", f"<i>{slogan}</i>"]

    occasion = cache.get("DEITY_ALL_OCCASIONS") or {}
    occ_title = str(occasion.get("occasion_title") or occasion.get("title") or "").strip()
    occ_detail = str(occasion.get("occasion_temple") or occasion.get("temple_highlight") or "").strip()
    generic_placeholders = {
        "",
        "none",
        "special panchangam observance & temple highlights.",
    }
    if occ_detail.lower() not in generic_placeholders:
        header = f"🛕 <b>Occasion &amp; Temple Note:</b> {html.escape(occ_title)}" if occ_title else "🛕 <b>Occasion &amp; Temple Note:</b>"
        lines.append(f"\n{header}\n{html.escape(occ_detail)}")
    return "\n".join(lines)

def build_weather_care_block(city_name: str, city: dict) -> str:
    weather_raw = str(city.get("weather") or "Pleasant morning").strip()
    rain_prob = city.get("rain_chance_pct")
    severity = str(city.get("condition_severity") or "").strip().upper()
    custom_care = str(city.get("care_line") or "").strip()

    prob_suffix = f" • {int(rain_prob)}% rain chance" if isinstance(rain_prob, (int, float)) else ""
    lines = [f"🌦️ <b>{html.escape(city_name)}:</b> {html.escape(weather_raw)}{html.escape(prob_suffix)}"]

    w_lower = weather_raw.lower()
    is_caution = severity in {"CAUTION_HEAVY_RAIN", "CAUTION_FOG", "CAUTION_SNOW"} or any(
        k in w_lower for k in ("heavy rain", "thunderstorm", "cyclone", "snow", "blizzard", "dense fog")
    )
    is_umbrella = (
        severity == "UMBRELLA"
        or (isinstance(rain_prob, (int, float)) and rain_prob >= 40)
        or any(k in w_lower for k in ("rain", "drizzle", "shower"))
    )

    if is_caution:
        lines.append("⚠️ <b>CAUTION:</b> Severe weather/low visibility possible—allow extra travel buffer and move carefully.")
        care = custom_care or "💛 <i>Care: Your safety comes first today—stay sheltered where needed and travel unhurriedly.</i>"
    elif is_umbrella:
        lines.append("☂️ <b>Umbrella Notice:</b> Carry an umbrella or light rain cover before stepping out.")
        care = custom_care or "💛 <i>Care: May your steps stay dry, safe, and peaceful as you head out today.</i>"
    else:
        care = custom_care or "💛 <i>Care: Wishing you a calm, healthy, and steady day ahead.</i>"

    lines.append(care)
    return "\n".join(lines)

def build_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("English", callback_data="lang:en"), InlineKeyboardButton("தமிழ் (Tamil)", callback_data="lang:ta")],
        [InlineKeyboardButton("हिन्दी (Hindi)", callback_data="lang:hi"), InlineKeyboardButton("తెలుగు (Telugu)", callback_data="lang:te")],
        [InlineKeyboardButton("ಕನ್ನಡ (Kannada)", callback_data="lang:kn"), InlineKeyboardButton("മലയാളം (Malayalam)", callback_data="lang:ml")]
    ])

def build_welcome_caption(first_name: str) -> str:
    safe_name = html.escape(first_name or "there")
    return (
        f"☀️ <b>FURLIS AURA</b>  |  <i>Morning Grace &amp; Daily Telemetry</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Namaskaram, <b>{safe_name}</b> 🙏\n\n"
        f"Every morning at <b>06:00 AM IST</b>, receive one calm, clear briefing tailored to your city &amp; Rasi:\n"
        f"• 🪔 <b>Day-of-Week Blessing</b> + relevant Temple &amp; Occasion alerts\n"
        f"• ⏳ <b>Auspicious Windows</b>, <b>Rasi Guidance</b> &amp; <b>Gold Rates</b>\n"
        f"• 🌦️ <b>Local Weather</b> with rain chances, umbrella/caution alerts &amp; care note\n\n"
        f"🔒 <i>DPDPA 2023: Only language, city &amp; Rasi are stored. Erase anytime via /delete_data.</i>\n\n"
        f"<b>Step 1 of 3 — Select your preferred language:</b>"
    )

def build_support_url(telegram_id: int, lang: str) -> str:
    template = SUPPORT_FORM_URLS.get(lang) or SUPPORT_FORM_URLS.get("en") or DEFAULT_SUPPORT_FORM_URL
    if not template:
        return "https://t.me"
    if "{uid}" in template:
        return template.format(uid=telegram_id)
    sep = "&" if "?" in template else "?"
    return f"{template}{sep}uid={telegram_id}"

def build_daily_action_keyboard(edition_date: str, telegram_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    upi_url = f"{UPI_CHECKOUT_BASE_URL}?uid={telegram_id}&ref={edition_date}"
    support_url = build_support_url(telegram_id, lang)
    keyboard = [
        [InlineKeyboardButton(f"⭐ {i}", callback_data=f"rate:{edition_date}:{i}") for i in range(1, 6)],
        [InlineKeyboardButton("📰 Other Services (12 Pillars & Social)", callback_data="menu:other_services")],
        [InlineKeyboardButton("💳 Pay (UPI)", url=upi_url)],
        [InlineKeyboardButton("🛠️ Support (Suggestion / Complaint)", url=support_url)],
    ]
    if lang != "en":
        keyboard.append([InlineKeyboardButton("🌐 Translate [ENG]", callback_data=f"translate:en:{edition_date}")])
    return InlineKeyboardMarkup(keyboard)

def send_founder_support_email(ticket_id: str, telegram_id: int, lang: str, category: str, message_text: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"[{ticket_id}] FURLIS AURA {category} — Telegram User {telegram_id} ({lang.upper()})"
    msg["From"] = SMTP_USER
    msg["To"] = FOUNDER_EMAIL
    msg.set_content(
        f"Service: FURLIS AURA\nTicket ID: {ticket_id}\nTelegram ID: {telegram_id}\nLanguage: {lang}\nCategory: {category}\n"
        f"Timestamp (UTC): {datetime.now(timezone.utc).isoformat()}\n\nMessage:\n{message_text}\n\n"
        f"To reply and close directly in user's Telegram chat:\n/reply {ticket_id} Thank you for reaching out to FURLIS AURA. Your request has been resolved."
    )
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to dispatch email for {ticket_id}: {e}")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    caption = build_welcome_caption(user.first_name if user else "there")
    keyboard = build_language_keyboard()
    if WELCOME_MEDIA_ID:
        try:
            await update.message.reply_animation(
                animation=WELCOME_MEDIA_ID,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return LANG
        except Exception as e:
            print(f"Welcome animation fallback triggered: {e}")
    await update.message.reply_text(caption, reply_markup=keyboard, parse_mode="HTML")
    return LANG

async def back_to_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    caption = build_welcome_caption(user.first_name if user else "there")
    keyboard = build_language_keyboard()
    if query.message and query.message.animation:
        await query.edit_message_caption(caption=caption, reply_markup=keyboard, parse_mode="HTML")
    else:
        await query.edit_message_text(text=caption, reply_markup=keyboard, parse_mode="HTML")
    return LANG

def render_location_prompt(lang_code: str) -> tuple[str, InlineKeyboardMarkup]:
    lang_label = html.escape(LANG_NAMES.get(lang_code, lang_code))
    text = (
        f"☀️ <b>FURLIS AURA</b>  |  <i>Setup (Step 2 of 3)</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✓ <b>Language:</b> {lang_label}\n\n"
        f"<b>Step 2 of 3 — Enter your City:</b>\n"
        f"<i>Example: Chennai, Mumbai, Bengaluru, Delhi</i>"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Language", callback_data="back:lang")]])
    return text, keyboard

async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang_code = query.data.split(":")[1]
    context.user_data["preferred_language"] = lang_code
    text, keyboard = render_location_prompt(lang_code)
    if query.message and query.message.animation:
        await query.edit_message_caption(caption=text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="HTML")
    return LOCATION

async def back_to_location_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang_code = context.user_data.get("preferred_language", "en")
    text, keyboard = render_location_prompt(lang_code)
    await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="HTML")
    return LOCATION

async def set_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city_input = update.message.text.strip().title()
    context.user_data["city"] = city_input
    lang_code = context.user_data.get("preferred_language", "en")
    lang_label = html.escape(LANG_NAMES.get(lang_code, lang_code))
    safe_city = html.escape(city_input)
    keyboard, row = [], []
    for rasi in RASI_LIST:
        row.append(InlineKeyboardButton(rasi, callback_data=f"rasi:{rasi}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("← Back to City", callback_data="back:location")])
    text = (
        f"☀️ <b>FURLIS AURA</b>  |  <i>Setup (Step 3 of 3)</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✓ <b>Language:</b> {lang_label}\n"
        f"✓ <b>City:</b> {safe_city}\n\n"
        f"<b>Step 3 of 3 — Select your Zodiac / Rasi:</b>"
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return RASI

async def set_rasi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    rasi = query.data.split(":")[1]
    context.user_data["rasi"] = rasi
    user = update.effective_user
    uid = user.id
    lang = context.user_data.get("preferred_language", "en")
    city = context.user_data.get("city", "Chennai")
    deity_mode = "AUTO"
    assert db_pool is not None
    await db_pool.execute(
        """
        INSERT INTO subscribers (telegram_id, first_name, preferred_language, city, rasi, deity_mode, frequency, is_active, consent_given_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, 1, TRUE, NOW(), NOW())
        ON CONFLICT (telegram_id) DO UPDATE SET
            first_name = EXCLUDED.first_name, preferred_language = EXCLUDED.preferred_language,
            city = EXCLUDED.city, rasi = EXCLUDED.rasi, deity_mode = EXCLUDED.deity_mode,
            is_active = TRUE, updated_at = NOW();
        """,
        uid, user.first_name, lang, city, rasi, deity_mode
    )
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    reply_markup = build_daily_action_keyboard(today_str, uid, lang)
    safe_lang = html.escape(LANG_NAMES.get(lang, lang))
    safe_city = html.escape(city)
    safe_rasi = html.escape(rasi)
    summary = (
        f"☀️ <b>FURLIS AURA</b>  |  <i>Morning Grace Activated</i> 🙏\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• <b>Language:</b> {safe_lang}\n"
        f"• <b>City:</b> {safe_city}\n"
        f"• <b>Rasi:</b> {safe_rasi}\n"
        f"• <b>Devotional Feed:</b> Day-of-Week Blessing + Relevant Occasion/Temple Alerts\n\n"
        f"Your daily card arrives every morning at <b>06:00 AM IST</b>.\n\n"
        f"{SHORT_DISCLAIMER}"
    )
    await query.edit_message_text(summary, reply_markup=reply_markup, parse_mode="HTML")
    return ConversationHandler.END

async def cancel_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Onboarding cancelled. Type /start anytime to begin again.")
    return ConversationHandler.END

async def delete_data_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    assert db_pool is not None
    await db_pool.execute("DELETE FROM subscribers WHERE telegram_id = $1;", uid)
    await update.message.reply_text(
        "🗑️ <b>Profile Erased:</b> Your user record and preferences have been permanently deleted per DPDPA guidelines.",
        parse_mode="HTML"
    )

async def capture_media_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or update.effective_user.id != FOUNDER_TELEGRAM_ID:
        return
    msg = update.message
    file_id = msg.animation.file_id if msg.animation else (msg.video.file_id if msg.video else None)
    media_type = "Animation / GIF" if msg.animation else ("Video" if msg.video else None)
    if file_id:
        await msg.reply_text(
            f"🎬 <b>{media_type} Captured</b>\n\nSet this in Render as <code>WELCOME_MEDIA_ID</code>:\n<code>{html.escape(file_id)}</code>",
            parse_mode="HTML"
        )

async def admin_reply_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or update.effective_user.id != FOUNDER_TELEGRAM_ID:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /reply <TKT-XXXXXXXX> <closure message>")
        return
    ticket_id = context.args[0].strip().upper()
    reply_body = " ".join(context.args[1:]).strip()
    assert db_pool is not None
    row = await db_pool.fetchrow("SELECT telegram_id, category FROM support_tickets WHERE ticket_id = $1;", ticket_id)
    if not row:
        await update.message.reply_text(f"Ticket {ticket_id} not found.")
        return
    await db_pool.execute("UPDATE support_tickets SET status = 'CLOSED', closed_at = NOW() WHERE ticket_id = $1;", ticket_id)
    user_notice = (
        f"📩 <b>FURLIS AURA Support Update — {html.escape(ticket_id)}</b> ({html.escape(row['category'])})\n\n"
        f"{html.escape(reply_body)}\n\nStatus: <b>Closed</b> ✅"
    )
    await context.bot.send_message(chat_id=row["telegram_id"], text=user_notice, parse_mode="HTML")
    await update.message.reply_text(f"✅ Reply sent to user {row['telegram_id']} and {ticket_id} marked CLOSED.")

async def handle_rating_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    edition_date_str, rating_val, uid = parts[1], int(parts[2]), query.from_user.id
    assert db_pool is not None
    try:
        await db_pool.execute(
            """
            INSERT INTO message_ratings (telegram_id, edition_date, rating, rated_at)
            VALUES ($1, $2::date, $3, NOW())
            ON CONFLICT (telegram_id, edition_date) DO UPDATE SET rating = EXCLUDED.rating, rated_at = NOW();
            """,
            uid, edition_date_str, rating_val
        )
        await query.answer(f"Thank you for rating today's FURLIS AURA card {rating_val}/5 stars! ⭐", show_alert=False)
    except Exception:
        await query.answer("Rating recorded!", show_alert=False)

async def handle_other_services_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    assert db_pool is not None
    row = await db_pool.fetchrow("SELECT subscribed_12_pillars FROM subscribers WHERE telegram_id = $1;", uid)
    is_subbed = row["subscribed_12_pillars"] if row else False
    toggle_txt = "🔕 Unsubscribe 12 Pillars Alerts" if is_subbed else "🔔 Subscribe 12 Pillars Alerts"
    keyboard = [
        [InlineKeyboardButton(toggle_txt, callback_data="sub:12pillars_toggle")],
        [InlineKeyboardButton("📺 YouTube", url="https://youtube.com"), InlineKeyboardButton("📸 Instagram", url="https://instagram.com")],
        [InlineKeyboardButton("🐦 X (Twitter)", url="https://x.com"), InlineKeyboardButton("💼 LinkedIn", url="https://linkedin.com")]
    ]
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_12pillars_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    uid = query.from_user.id
    assert db_pool is not None
    row = await db_pool.fetchrow("SELECT subscribed_12_pillars FROM subscribers WHERE telegram_id = $1;", uid)
    curr = row["subscribed_12_pillars"] if row else False
    new_val = not curr
    await db_pool.execute("UPDATE subscribers SET subscribed_12_pillars = $1 WHERE telegram_id = $2;", new_val, uid)
    status_txt = "subscribed to" if new_val else "unsubscribed from"
    await query.answer(f"You have {status_txt} FURLIS AURA 12 Pillars News Alerts!", show_alert=True)

async def handle_translate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    target_lang, edition_date_str = parts[1], parts[2]
    assert db_pool is not None
    rows = await db_pool.fetch("SELECT bucket_key, payload_json FROM daily_shared_cache WHERE edition_date = $1::date AND language = $2;", edition_date_str, target_lang)
    if not rows:
        rows = await db_pool.fetch("SELECT bucket_key, payload_json FROM daily_shared_cache WHERE edition_date = $1::date AND language = 'en';", edition_date_str)
    if not rows:
        await query.answer("English translation unavailable for this edition.", show_alert=True)
        return
    await query.answer("Translated to English", show_alert=False)
    cache = {r["bucket_key"]: json.loads(r["payload_json"]) if isinstance(r["payload_json"], str) else r["payload_json"] for r in rows}
    devotional_html = build_devotional_block(cache)
    gold = cache.get("GOLD_INR", {})
    quote_block = cache.get("FAMOUS_QUOTE", {})
    translated_txt = (
        f"🌐 <b>FURLIS AURA — English Translation ({html.escape(edition_date_str)})</b>\n\n"
        f"{devotional_html}\n\n"
        f"🪙 <b>Gold Rates:</b> {html.escape(str(gold.get('board_summary', '')))}\n\n"
        f"💡 \"{html.escape(str(quote_block.get('quote', '')))}\" — {html.escape(str(quote_block.get('author', '')))}\n\n"
        f"{SHORT_DISCLAIMER}"
    )
    await context.bot.send_message(chat_id=query.from_user.id, text=translated_txt, parse_mode="HTML")

async def handle_health_check(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "FURLIS AURA Web Server", "utc": datetime.now(timezone.utc).isoformat()})

async def handle_google_form_support_webhook(request: web.Request) -> web.Response:
    if request.headers.get("X-Webhook-Secret") != SUPPORT_WEBHOOK_SECRET:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
    data = await request.json()
    raw_uid = str(data.get("telegram_id", "")).strip()
    category = str(data.get("category", "Suggestion")).strip()
    message_text = str(data.get("message", "")).strip()
    lang = str(data.get("language", "en")).strip().lower() or "en"
    if not raw_uid.isdigit() or not message_text:
        return web.json_response({"ok": False, "error": "invalid_payload"}, status=400)
    telegram_id = int(raw_uid)
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    assert db_pool is not None
    row = await db_pool.fetchrow("SELECT preferred_language FROM subscribers WHERE telegram_id = $1;", telegram_id)
    if row and row["preferred_language"]:
        lang = row["preferred_language"]
    await db_pool.execute("INSERT INTO support_tickets (ticket_id, telegram_id, preferred_language, category, message_text, status, email_dispatched, created_at) VALUES ($1, $2, $3, $4, $5, 'OPEN', TRUE, NOW());", ticket_id, telegram_id, lang, category, message_text)
    bot = request.app["tg_app"].bot
    ack_text = (
        f"✅ <b>FURLIS AURA Support Ticket Logged:</b> <code>{html.escape(ticket_id)}</code>\n\n"
        f"• <b>Category:</b> {html.escape(category)}\n"
        f"We have received your request and will respond directly in this chat."
    )
    try:
        await bot.send_message(chat_id=telegram_id, text=ack_text, parse_mode="HTML")
    except Exception:
        pass
    await asyncio.to_thread(send_founder_support_email, ticket_id, telegram_id, lang, category, message_text)
    return web.json_response({"ok": True, "ticket_id": ticket_id})

async def main() -> None:
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    tg_app = ApplicationBuilder().token(BOT_TOKEN).read_timeout(60).write_timeout(60).connect_timeout(30).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_cmd)],
        states={
            LANG: [CallbackQueryHandler(set_language_callback, pattern=r"^lang:")],
            LOCATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_location),
                CallbackQueryHandler(back_to_language_callback, pattern=r"^back:lang$")
            ],
            RASI: [
                CallbackQueryHandler(set_rasi_callback, pattern=r"^rasi:"),
                CallbackQueryHandler(back_to_location_callback, pattern=r"^back:location$")
            ]
        },
        fallbacks=[
            CommandHandler("start", start_cmd),
            CommandHandler("cancel", cancel_onboarding)
        ]
    )
    tg_app.add_handler(conv_handler)
    tg_app.add_handler(CommandHandler("delete_data", delete_data_cmd))
    tg_app.add_handler(CommandHandler("reply", admin_reply_ticket))
    tg_app.add_handler(MessageHandler(filters.ANIMATION | filters.VIDEO, capture_media_file_id))
    tg_app.add_handler(CallbackQueryHandler(handle_rating_callback, pattern=r"^rate:"))
    tg_app.add_handler(CallbackQueryHandler(handle_other_services_callback, pattern=r"^menu:other_services$"))
    tg_app.add_handler(CallbackQueryHandler(handle_12pillars_toggle_callback, pattern=r"^sub:12pillars_toggle$"))
    tg_app.add_handler(CallbackQueryHandler(handle_translate_callback, pattern=r"^translate:"))
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling()
    web_app = web.Application()
    web_app["tg_app"] = tg_app
    web_app.router.add_get("/health", handle_health_check)
    web_app.router.add_post("/webhook/google-form-support", handle_google_form_support_webhook)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"FURLIS AURA Bot Web Service running on port {PORT}...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
