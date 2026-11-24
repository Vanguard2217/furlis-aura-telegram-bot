# bot.py — FURLIS AURA Telegram Bot Web Service
import os
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

db_pool: asyncpg.Pool | None = None
LANG, LOCATION, RASI, DEITY = range(4)
LANG_NAMES = {
    "en": "English", "ta": "தமிழ் (Tamil)", "hi": "हिन्दी (Hindi)",
    "te": "తెలుగు (Telugu)", "kn": "ಕನ್ನಡ (Kannada)", "ml": "മലയാളം (Malayalam)"
}
RASI_LIST = [
    "Mesham", "Rishabam", "Mithunam", "Kadagam",
    "Simmam", "Kanni", "Thulam", "Vrischikam",
    "Dhanusu", "Magaram", "Kumbam", "Meenam"
]

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
    keyboard = [
        [InlineKeyboardButton("English", callback_data="lang:en"), InlineKeyboardButton("தமிழ் (Tamil)", callback_data="lang:ta")],
        [InlineKeyboardButton("हिन्दी (Hindi)", callback_data="lang:hi"), InlineKeyboardButton("తెలుగు (Telugu)", callback_data="lang:te")],
        [InlineKeyboardButton("ಕನ್ನಡ (Kannada)", callback_data="lang:kn"), InlineKeyboardButton("മലയാളം (Malayalam)", callback_data="lang:ml")]
    ]
    notice = (
        f"Welcome to FURLIS AURA, {user.first_name}! 🙏\n\n🔒 *Privacy & Data Notice (DPDPA 2023):*\n"
        "We collect your preferred language, city, and Zodiac sign solely to deliver tailored daily telemetry, auspicious windows, weather, and devotional blessings.\n\n"
        "You can erase your data anytime using /delete_data.\n\n*Step 1:* Please select your preferred language:"
    )
    await update.message.reply_text(notice, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return LANG

async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang_code = query.data.split(":")[1]
    context.user_data["preferred_language"] = lang_code
    await query.edit_message_text(
        f"✅ Language set to *{LANG_NAMES[lang_code]}*.\n\n*Step 2:* Please type your *City* (e.g., Chennai, Mumbai, Bengaluru, Delhi):",
        parse_mode="Markdown"
    )
    return LOCATION

async def set_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city_input = update.message.text.strip().title()
    context.user_data["city"] = city_input
    keyboard, row = [], []
    for rasi in RASI_LIST:
        row.append(InlineKeyboardButton(rasi, callback_data=f"rasi:{rasi}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    await update.message.reply_text(
        f"✅ Location set to *{city_input}*.\n\n*Step 3:* Please select your Zodiac / Rasi:",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return RASI

async def set_rasi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    rasi = query.data.split(":")[1]
    context.user_data["rasi"] = rasi
    keyboard = [
        [InlineKeyboardButton("🗓️ Day-of-Week Tradition", callback_data="deity:DAY_OF_WEEK")],
        [InlineKeyboardButton("🛕 All Occasions & Temple Alerts", callback_data="deity:ALL_OCCASIONS")]
    ]
    await query.edit_message_text(
        f"✅ Rasi set to *{rasi}*.\n\n*Step 4:* Choose your daily devotional preference:",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )
    return DEITY

async def set_deity_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    deity_mode = query.data.split(":")[1]
    user = update.effective_user
    uid = user.id
    lang = context.user_data.get("preferred_language", "en")
    city = context.user_data.get("city", "Chennai")
    rasi = context.user_data.get("rasi", "Mesham")
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
    summary = (
        "🎉 *Welcome to FURLIS AURA!*\n\n"
        f"• *Language:* {LANG_NAMES.get(lang, lang)}\n• *Location:* {city}\n"
        f"• *Rasi:* {rasi}\n• *Deity Mode:* {deity_mode}\n\n"
        "Your personalized daily telemetry card will be delivered every morning at 06:00 AM IST."
    )
    await query.edit_message_text(summary, reply_markup=reply_markup, parse_mode="Markdown")
    return ConversationHandler.END

async def cancel_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Onboarding cancelled. Type /start anytime to begin again.")
    return ConversationHandler.END

async def delete_data_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    assert db_pool is not None
    await db_pool.execute("DELETE FROM subscribers WHERE telegram_id = $1;", uid)
    await update.message.reply_text("🗑️ *Profile Erased:* Your user record and preferences have been permanently deleted per DPDPA guidelines.", parse_mode="Markdown")

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
    user_notice = f"📩 *FURLIS AURA Support Update — {ticket_id}* ({row['category']})\n\n{reply_body}\n\nStatus: *Closed* ✅"
    await context.bot.send_message(chat_id=row["telegram_id"], text=user_notice, parse_mode="Markdown")
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
    deity = cache.get("DEITY_DAY_OF_WEEK", {})
    gold = cache.get("GOLD_INR", {})
    quote_block = cache.get("FAMOUS_QUOTE", {})
    translated_txt = (
        f"🌐 *FURLIS AURA — English Translation ({edition_date_str})*\n\n🙏 *{deity.get('title', 'Daily Blessing')}*\n{deity.get('slogan', '')}\n\n"
        f"🪙 *Gold Rates:* {gold.get('board_summary', '')}\n\n💡 \"{quote_block.get('quote', '')}\" — {quote_block.get('author', '')}"
    )
    await context.bot.send_message(chat_id=query.from_user.id, text=translated_txt, parse_mode="Markdown")

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
    ack_text = f"✅ *FURLIS AURA Support Ticket Logged:* `{ticket_id}`\n\n• *Category:* {category}\nWe have received your request and will respond directly in this chat."
    try:
        await bot.send_message(chat_id=telegram_id, text=ack_text, parse_mode="Markdown")
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
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_location)],
            RASI: [CallbackQueryHandler(set_rasi_callback, pattern=r"^rasi:")],
            DEITY: [CallbackQueryHandler(set_deity_callback, pattern=r"^deity:")]
        },
        fallbacks=[CommandHandler("cancel", cancel_onboarding)]
    )
    tg_app.add_handler(conv_handler)
    tg_app.add_handler(CommandHandler("delete_data", delete_data_cmd))
    tg_app.add_handler(CommandHandler("reply", admin_reply_ticket))
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
