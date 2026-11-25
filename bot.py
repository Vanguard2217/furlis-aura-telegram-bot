# bot.py — AURA Telegram Bot Web Service
import os
import re
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

DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

SHORT_DISCLAIMER = (
    "⚖️ <i>Disclaimer: Devotional, Rasi/WoW, gold/silver, weather &amp; alert details are for general "
    "informational guidance only—not financial, medical, legal, travel, or emergency safety advice. "
    "Please verify critical decisions independently.</i>"
)

db_pool: asyncpg.Pool | None = None
LANG, DOB, LOCATION, RASI, EDIT_VALUE = range(5)

LANG_NAMES = {
    "en": "English",
    "ta": "தமிழ் (Tamil)",
    "hi": "हिन्दी (Hindi)",
    "te": "తెలుగు (Telugu)",
    "kn": "ಕನ್ನಡ (Kannada)",
    "ml": "മലയാളം (Malayalam)",
}

UI_STRINGS = {
    "en": {
        "ask_dob": "Enter your <b>Date of Birth</b> (e.g., <code>15-08-1985</code>):",
        "invalid_dob": "Please enter a valid Date of Birth (e.g., <code>15-08-1985</code> or <code>1985-08-15</code>):",
        "ask_city": (
            "Enter your <b>Locality &amp; City</b> (or just your <b>City</b>):\n"
            "<i>Example: Ambattur, Chennai, Adyar, Chennai, or Chennai</i>\n"
            "<i>Why? Adding your locality gives sharper local weather &amp; rain updates.</i>"
        ),
        "ask_rasi": "Select your <b>Zodiac / Rasi</b>:",
        "back_lang": "← Back to Language",
        "back_dob": "← Back to Date of Birth",
        "back_city": "← Back to Locality / City",
        "rate_toast": "Thank you for rating today's AURA card {val}/5 stars! ⭐",
        "other_services": "📰 Other Services (12 Pillars & Social)",
        "pay_upi": "💳 Pay (UPI)",
        "support": "🛠️ Support (Suggestion / Complaint)",
        "profile_btn": "👤 Profile",
        "settings_btn": "⚙️ Settings",
        "translate_eng": "🌐 Translate [ENG]",
        "sub_12": "🔔 Subscribe 12 Pillars Alerts",
        "unsub_12": "🔕 Unsubscribe 12 Pillars Alerts",
        "erased": "🗑️ <b>Profile Erased:</b> Your profile, Date of Birth, locality/city, and preferences have been permanently deleted per DPDPA 2023.",
    },
    "ta": {
        "ask_dob": "உங்கள் <b>பிறந்த தேதியை</b> உள்ளிடவும் (உதா: <code>15-08-1985</code>):",
        "invalid_dob": "சரியான பிறந்த தேதியை உள்ளிடவும் (உதா: <code>15-08-1985</code>):",
        "ask_city": (
            "உங்கள் <b>பகுதி மற்றும் நகரத்தை</b> உள்ளிடவும் (அல்லது <b>நகரம்</b> மட்டும்):\n"
            "<i>உதாரணம்: அம்பத்தூர், சென்னை, அடையாறு, சென்னை, அல்லது சென்னை</i>\n"
            "<i>ஏன்? பகுதியைச் சேர்த்தால் அருகிலுள்ள மழை மற்றும் வானிலை தகவல் துல்லியமாக இருக்கும்.</i>"
        ),
        "ask_rasi": "உங்கள் <b>ராசியைத்</b> தேர்ந்தெடுக்கவும்:",
        "back_lang": "← மொழிக்குத் திரும்புக",
        "back_dob": "← பிறந்த தேதிக்குத் திரும்புக",
        "back_city": "← பகுதி / நகரத்திற்குத் திரும்புக",
        "rate_toast": "இன்றைய AURA பதிவுக்கு {val}/5 நட்சத்திரம் அளித்தமைக்கு நன்றி! ⭐",
        "other_services": "📰 மற்ற சேவைகள் (12 தூண்கள் & சமூகம்)",
        "pay_upi": "💳 UPI மூலம் செலுத்துக",
        "support": "🛠️ உதவி (கருத்து / புகார்)",
        "profile_btn": "👤 சுயவிவரம்",
        "settings_btn": "⚙️ அமைப்புகள்",
        "translate_eng": "🌐 Translate [ENG]",
        "sub_12": "🔔 12 தூண்கள் அறிவிப்பில் சேர்க",
        "unsub_12": "🔕 12 தூண்கள் அறிவிப்பிலிருந்து விலகுக",
        "erased": "🗑️ <b>தகவல்கள் நீக்கப்பட்டன:</b> DPDPA 2023 விதிகளின்படி உங்கள் விவரங்கள் நிரந்தரமாக நீக்கப்பட்டன.",
    },
    "hi": {
        "ask_dob": "अपनी <b>जन्म तिथि (DOB)</b> दर्ज करें (उदा: <code>15-08-1985</code>):",
        "invalid_dob": "कृपया मान्य जन्म तिथि दर्ज करें (उदा: <code>15-08-1985</code>):",
        "ask_city": (
            "अपना <b>क्षेत्र और शहर</b> दर्ज करें (या केवल <b>शहर</b>):\n"
            "<i>उदाहरण: Ambattur, Chennai, Adyar, Chennai, या Chennai</i>\n"
            "<i>क्यों? क्षेत्र जोड़ने से आपके इलाके के अनुसार मौसम की जानकारी अधिक सटीक मिलती है।</i>"
        ),
        "ask_rasi": "अपनी <b>राशि</b> चुनें:",
        "back_lang": "← भाषा पर वापस जाएं",
        "back_dob": "← जन्म तिथि पर वापस जाएं",
        "back_city": "← क्षेत्र / शहर पर वापस जाएं",
        "rate_toast": "आज के AURA संदेश को {val}/5 रेटिंग देने के लिए धन्यवाद! ⭐",
        "other_services": "📰 अन्य सेवाएं (12 पिलर्स व सोशल)",
        "pay_upi": "💳 UPI से भुगतान करें",
        "support": "🛠️ सहायता (सुझाव / शिकायत)",
        "profile_btn": "👤 प्रोफ़ाइल",
        "settings_btn": "⚙️ सेटिंग्स",
        "translate_eng": "🌐 Translate [ENG]",
        "sub_12": "🔔 12 पिलर्स अलर्ट सब्सक्राइब करें",
        "unsub_12": "🔕 12 पिलर्स अलर्ट अनसब्सक्राइब करें",
        "erased": "🗑️ <b>डेटा हटाया गया:</b> DPDPA 2023 के तहत आपका प्रोफ़ाइल और विवरण स्थायी रूप से हटा दिया गया है।",
    },
    "te": {
        "ask_dob": "మీ <b>పుట్టిన తేదీని (DOB)</b> నమోదు చేయండి (ఉదా: <code>15-08-1985</code>):",
        "invalid_dob": "దయచేసి సరైన పుట్టిన తేదీని నమోదు చేయండి (ఉదా: <code>15-08-1985</code>):",
        "ask_city": (
            "మీ <b>ప్రాంతం మరియు నగరాన్ని</b> నమోదు చేయండి (లేదా <b>నగరం</b> మాత్రమే):\n"
            "<i>ఉదాహరణ: Ambattur, Chennai, Adyar, Chennai, లేదా Chennai</i>\n"
            "<i>ఎందుకు? ప్రాంతం చేరిస్తే స్థానిక వాతావరణ &amp; వర్ష సమాచారం మరింత ఖచ్చితంగా ఉంటుంది.</i>"
        ),
        "ask_rasi": "మీ <b>రాశిని</b> ఎంచుకోండి:",
        "back_lang": "← భాషకు తిరిగి వెళ్ళండి",
        "back_dob": "← పుట్టిన తేదీకి తిరిగి వెళ్ళండి",
        "back_city": "← ప్రాంతం / నగరానికి తిరిగి వెళ్ళండి",
        "rate_toast": "నేటి AURA కార్డ్‌కు {val}/5 రేటింగ్ ఇచ్చినందుకు ధన్యవాదాలు! ⭐",
        "other_services": "📰 ఇతర సేవలు (12 పిల్లర్స్ & సోషల్)",
        "pay_upi": "💳 UPI ద్వారా చెల్లించండి",
        "support": "🛠️ సహాయం (సలహా / ఫిర్యాదు)",
        "profile_btn": "👤 ప్రొఫైల్",
        "settings_btn": "⚙️ సెట్టింగ్స్",
        "translate_eng": "🌐 Translate [ENG]",
        "sub_12": "🔔 12 పిల్లర్స్ అలర్ట్స్‌లో చేరండి",
        "unsub_12": "🔕 12 పిల్లర్స్ అలర్ట్స్ నుండి నిష్క్రమించండి",
        "erased": "🗑️ <b>డేటా తొలగించబడింది:</b> DPDPA 2023 ప్రకారం మీ వివరాలు శాశ్వతంగా తొలగించబడ్డాయి.",
    },
    "kn": {
        "ask_dob": "ನಿಮ್ಮ <b>ಜನ್ಮ ದಿನಾಂಕವನ್ನು (DOB)</b> ನಮೂದಿಸಿ (ಉದಾ: <code>15-08-1985</code>):",
        "invalid_dob": "ದಯವಿಟ್ಟು ಸರಿಯಾದ ಜನ್ಮ ದಿನಾಂಕವನ್ನು ನಮೂದಿಸಿ (ಉದಾ: <code>15-08-1985</code>):",
        "ask_city": (
            "ನಿಮ್ಮ <b>ಪ್ರದೇಶ ಮತ್ತು ನಗರವನ್ನು</b> ನಮೂದಿಸಿ (ಅಥವಾ <b>ನಗರ</b> ಮಾತ್ರ):\n"
            "<i>ಉದಾಹರಣೆ: Ambattur, Chennai, Adyar, Chennai, ಅಥವಾ Chennai</i>\n"
            "<i>ಏಕೆ? ಪ್ರದೇಶ ಸೇರಿಸಿದರೆ ಸ್ಥಳೀಯ ಹವಾಮಾನ ಮತ್ತು ಮಳೆ ಮಾಹಿತಿ ಹೆಚ್ಚು ನಿಖರವಾಗಿರುತ್ತದೆ.</i>"
        ),
        "ask_rasi": "ನಿಮ್ಮ <b>ರಾಶಿಯನ್ನು</b> ಆಯ್ಕೆಮಾಡಿ:",
        "back_lang": "← ಭಾಷೆಗೆ ಹಿಂತಿರುಗಿ",
        "back_dob": "← ಜನ್ಮ ದಿನಾಂಕಕ್ಕೆ ಹಿಂತಿರುಗಿ",
        "back_city": "← ಪ್ರದೇಶ / ನಗರಕ್ಕೆ ಹಿಂತಿರುಗಿ",
        "rate_toast": "ಇಂದಿನ AURA ಕಾರ್ಡ್‌ಗೆ {val}/5 ರೇಟಿಂಗ್ ನೀಡಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು! ⭐",
        "other_services": "📰 ಇತರೆ ಸೇವೆಗಳು (12 ಪಿಲ್ಲರ್ಸ್ & ಸೋಶಿಯಲ್)",
        "pay_upi": "💳 UPI ಮೂಲಕ ಪಾವತಿಸಿ",
        "support": "🛠️ ಬೆಂಬಲ (ಸಲಹೆ / ದೂರು)",
        "profile_btn": "👤 ಪ್ರೊಫೈಲ್",
        "settings_btn": "⚙️ ಸೆಟ್ಟಿಂಗ್ಸ್",
        "translate_eng": "🌐 Translate [ENG]",
        "sub_12": "🔔 12 ಪಿಲ್ಲರ್ಸ್ ಅಲರ್ಟ್‌ಗಳಿಗೆ ಸೇರಿ",
        "unsub_12": "🔕 12 ಪಿಲ್ಲರ್ಸ್ ಅಲರ್ಟ್‌ಗಳಿಂದ ನಿರ್ಗಮಿಸಿ",
        "erased": "🗑️ <b>ಮಾಹಿತಿ ಅಳಿಸಲಾಗಿದೆ:</b> DPDPA 2023 ಪ್ರಕಾರ ನಿಮ್ಮ ಪ್ರೊಫೈಲ್ ಶಾಶ್ವತವಾಗಿ ಅಳಿಸಲಾಗಿದೆ.",
    },
    "ml": {
        "ask_dob": "നിങ്ങളുടെ <b>ജനനത്തീയതി (DOB)</b> നൽകുക (ഉദാ: <code>15-08-1985</code>):",
        "invalid_dob": "ശരിയായ ജനനത്തീയതി നൽകുക (ഉദാ: <code>15-08-1985</code>):",
        "ask_city": (
            "നിങ്ങളുടെ <b>പ്രദേശവും നഗരവും</b> നൽകുക (അല്ലെങ്കിൽ <b>നഗരം</b> മാത്രം):\n"
            "<i>ഉദാഹരണം: Ambattur, Chennai, Adyar, Chennai, അല്ലെങ്കിൽ Chennai</i>\n"
            "<i>എന്തുകൊണ്ട്? പ്രദേശം ചേർത്താൽ പ്രാദേശിക കാലാവസ്ഥയും മഴ വിവരവും കൂടുതൽ കൃത്യമാകും.</i>"
        ),
        "ask_rasi": "നിങ്ങളുടെ <b>രാശി</b> തിരഞ്ഞെടുക്കുക:",
        "back_lang": "← ഭാഷയിലേക്ക് മടങ്ങുക",
        "back_dob": "← ജനനത്തീയതിയിലേക്ക് മടങ്ങുക",
        "back_city": "← പ്രദേശം / നഗരത്തിലേക്ക് മടങ്ങുക",
        "rate_toast": "ഇന്നത്തെ AURA കാർഡിന് {val}/5 റേറ്റിംഗ് നൽകിയതിന് നന്ദി! ⭐",
        "other_services": "📰 മറ്റ് സേവനങ്ങൾ (12 പില്ലേഴ്സ് & സോഷ്യൽ)",
        "pay_upi": "💳 UPI വഴി പണമടയ്ക്കുക",
        "support": "🛠️ സഹായം (നിർദ്ദേശം / പരാതി)",
        "profile_btn": "👤 പ്രൊഫൈൽ",
        "settings_btn": "⚙️ ക്രമീകരണങ്ങൾ",
        "translate_eng": "🌐 Translate [ENG]",
        "sub_12": "🔔 12 പില്ലേഴ്സ് അലർട്ടുകളിൽ ചേരുക",
        "unsub_12": "🔕 12 പില്ലേഴ്സ് അലർട്ടുകളിൽ നിന്ന് ഒഴിവാക്കുക",
        "erased": "🗑️ <b>ഡാറ്റ മായ്ച്ചു:</b> DPDPA 2023 പ്രകാരം നിങ്ങളുടെ വിവരങ്ങൾ ശാശ്വതമായി നീക്കം ചെയ്തു.",
    },
}

RASI_LIST = [
    "Mesham", "Rishabam", "Mithunam", "Kadagam",
    "Simmam", "Kanni", "Thulam", "Vrischikam",
    "Dhanusu", "Magaram", "Kumbam", "Meenam",
]


def t(lang: str, key: str) -> str:
    pack = UI_STRINGS.get(lang) or UI_STRINGS["en"]
    return pack.get(key) or UI_STRINGS["en"][key]


def format_location_input(raw_text: str) -> str:
    parts = [re.sub(r"\s+", " ", p).strip() for p in raw_text.split(",", 1)]
    formatted = [p.title() for p in parts if p]
    return ", ".join(formatted) if formatted else "Chennai"


def normalize_dob(raw_dob: str) -> str | None:
    cleaned = raw_dob.strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            if 1900 <= dt.year <= datetime.now(timezone.utc).year:
                return dt.strftime("%d-%m-%Y")
        except ValueError:
            continue
    return None


def build_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("English", callback_data="lang:en"), InlineKeyboardButton("தமிழ் (Tamil)", callback_data="lang:ta")],
        [InlineKeyboardButton("हिन्दी (Hindi)", callback_data="lang:hi"), InlineKeyboardButton("తెలుగు (Telugu)", callback_data="lang:te")],
        [InlineKeyboardButton("ಕನ್ನಡ (Kannada)", callback_data="lang:kn"), InlineKeyboardButton("മലയാളം (Malayalam)", callback_data="lang:ml")],
    ])


def build_language_intro_text() -> str:
    return (
        f"ॐ <b>AURA</b>  |  <i>Morning Grace &amp; Daily Blessing</i>\n"
        f"{DIVIDER}\n\n"
        f"Select your preferred language to begin / உங்கள் மொழിയെத் தேர்ந்தெடுக்கவும் / अपनी भाषा चुनें:"
    )


def build_welcome_card(first_name: str, lang: str = "en") -> str:
    safe_name = html.escape(first_name or "there")
    return (
        f"ॐ <b>AURA</b>  |  <i>Morning Grace &amp; Daily Blessing</i>\n"
        f"{DIVIDER}\n\n"
        f"Namaskaram, <b>{safe_name}</b> 🙏\n\n"
        f"Every morning at <b>04:30 AM IST</b>, receive one calm and blessed message to start your day with <b>Ashirvad:</b>\n\n"
        f"• 🪔 <b>Daily Blessing</b> + 🛕 <b>Temple &amp; Occasion Alerts</b>\n\n"
        f"• ⏳ <b>Auspicious Timing</b> + ✨ <b>WoW (Words of Wisdom, as per Rasi)</b> + 🪙 <b>Gold Rates</b>\n\n"
        f"• ✨ <b>WoW</b> — Words of Wisdom, as per your Rasi\n\n"
        f"• 🪙 <b>Gold &amp; Silver Rates</b>\n\n"
        f"• 🌦️ <b>Weather (Plan Your Day)</b> — rain chances, umbrella/caution alerts &amp; care note\n\n"
        f"🔒 <i>DPDPA 2023: Only Language, Date of Birth, City &amp; Rasi are stored. Erase anytime via <a href=\"https://t.me\">DELETE</a> (or /delete_data).</i>\n\n"
        f"<b>Step 1 of 3 — {t(lang, 'ask_dob')}</b>"
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
        [
            InlineKeyboardButton(t(lang, "profile_btn"), callback_data="menu:profile"),
            InlineKeyboardButton(t(lang, "settings_btn"), callback_data="menu:settings"),
        ],
        [InlineKeyboardButton(t(lang, "other_services"), callback_data="menu:other_services")],
        [InlineKeyboardButton(t(lang, "pay_upi"), url=upi_url)],
        [InlineKeyboardButton(t(lang, "support"), url=support_url)],
    ]
    if lang != "en":
        keyboard.append([InlineKeyboardButton(t(lang, "translate_eng"), callback_data=f"translate:en:{edition_date}")])
    return InlineKeyboardMarkup(keyboard)


def send_founder_support_email(ticket_id: str, telegram_id: int, lang: str, category: str, message_text: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"[{ticket_id}] AURA {category} — Telegram User {telegram_id} ({lang.upper()})"
    msg["From"] = SMTP_USER
    msg["To"] = FOUNDER_EMAIL
    msg.set_content(
        f"Service: AURA\nTicket ID: {ticket_id}\nTelegram ID: {telegram_id}\nLanguage: {lang}\nCategory: {category}\n"
        f"Timestamp (UTC): {datetime.now(timezone.utc).isoformat()}\n\nMessage:\n{message_text}\n\n"
        f"To reply and close directly in user's Telegram chat:\n/reply {ticket_id} Thank you for reaching out to AURA. Your request has been resolved."
    )
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to dispatch email for {ticket_id}: {e}")


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    text = build_language_intro_text()
    keyboard = build_language_keyboard()
    if WELCOME_MEDIA_ID:
        try:
            await update.message.reply_animation(
                animation=WELCOME_MEDIA_ID,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return LANG
        except Exception as e:
            print(f"Welcome animation fallback triggered: {e}")
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
    return LANG


async def back_to_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    text = build_language_intro_text()
    keyboard = build_language_keyboard()
    if query.message and query.message.animation:
        await query.edit_message_caption(caption=text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="HTML")
    return LANG


async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang_code = query.data.split(":", 1)[1]
    context.user_data["preferred_language"] = lang_code
    user = update.effective_user
    welcome_card = build_welcome_card(user.first_name if user else "there", lang_code)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang_code, "back_lang"), callback_data="back:lang")]])
    if query.message and query.message.animation:
        await query.edit_message_caption(caption=welcome_card, reply_markup=keyboard, parse_mode="HTML")
    else:
        await query.edit_message_text(text=welcome_card, reply_markup=keyboard, parse_mode="HTML")
    return DOB


def render_city_prompt(lang_code: str, dob_str: str) -> tuple[str, InlineKeyboardMarkup]:
    lang_label = html.escape(LANG_NAMES.get(lang_code, lang_code))
    safe_dob = html.escape(dob_str)
    text = (
        f"ॐ <b>AURA</b>  |  <i>Setup (Step 2 of 3)</i>\n"
        f"{DIVIDER}\n\n"
        f"✓ <b>Language:</b> {lang_label}\n\n"
        f"✓ <b>Date of Birth:</b> {safe_dob}\n\n"
        f"<b>Step 2 of 3 — {t(lang_code, 'ask_city')}</b>"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang_code, "back_dob"), callback_data="back:dob")]])
    return text, keyboard


async def set_dob(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang_code = context.user_data.get("preferred_language", "en")
    parsed_dob = normalize_dob(update.message.text or "")
    if not parsed_dob:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang_code, "back_lang"), callback_data="back:lang")]])
        await update.message.reply_text(t(lang_code, "invalid_dob"), reply_markup=keyboard, parse_mode="HTML")
        return DOB
    context.user_data["dob"] = parsed_dob
    text, keyboard = render_city_prompt(lang_code, parsed_dob)
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
    return LOCATION


async def back_to_dob_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang_code = context.user_data.get("preferred_language", "en")
    user = update.effective_user
    welcome_card = build_welcome_card(user.first_name if user else "there", lang_code)
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang_code, "back_lang"), callback_data="back:lang")]])
    await query.edit_message_text(text=welcome_card, reply_markup=keyboard, parse_mode="HTML")
    return DOB


async def back_to_location_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang_code = context.user_data.get("preferred_language", "en")
    dob_str = context.user_data.get("dob", "")
    text, keyboard = render_city_prompt(lang_code, dob_str)
    await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="HTML")
    return LOCATION


async def set_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    location_label = format_location_input(update.message.text or "")
    context.user_data["city"] = location_label
    lang_code = context.user_data.get("preferred_language", "en")
    lang_label = html.escape(LANG_NAMES.get(lang_code, lang_code))
    safe_dob = html.escape(context.user_data.get("dob", ""))
    safe_loc = html.escape(location_label)

    keyboard, row = [], []
    for rasi in RASI_LIST:
        row.append(InlineKeyboardButton(rasi, callback_data=f"rasi:{rasi}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(t(lang_code, "back_city"), callback_data="back:location")])

    text = (
        f"ॐ <b>AURA</b>  |  <i>Setup (Step 3 of 3)</i>\n"
        f"{DIVIDER}\n\n"
        f"✓ <b>Language:</b> {lang_label}\n\n"
        f"✓ <b>Date of Birth:</b> {safe_dob}\n\n"
        f"✓ <b>Locality / City:</b> {safe_loc}\n\n"
        f"<b>Step 3 of 3 — {t(lang_code, 'ask_rasi')}</b>"
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return RASI


async def set_rasi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    rasi = query.data.split(":", 1)[1]
    context.user_data["rasi"] = rasi

    user = update.effective_user
    uid = user.id
    lang = context.user_data.get("preferred_language", "en")
    dob_str = context.user_data.get("dob", "")
    location_label = context.user_data.get("city", "Chennai")
    deity_mode = "AUTO"
    freq = 1 if not FEATURE_FREQUENCY_ACTIVE else context.user_data.get("frequency", 1)

    assert db_pool is not None
    await db_pool.execute(
        """
        INSERT INTO subscribers (
            telegram_id, first_name, preferred_language, dob, city, rasi,
            deity_mode, frequency, is_active, consent_given_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, TRUE, NOW(), NOW())
        ON CONFLICT (telegram_id) DO UPDATE SET
            first_name = EXCLUDED.first_name,
            preferred_language = EXCLUDED.preferred_language,
            dob = EXCLUDED.dob,
            city = EXCLUDED.city,
            rasi = EXCLUDED.rasi,
            deity_mode = EXCLUDED.deity_mode,
            frequency = EXCLUDED.frequency,
            is_active = TRUE,
            updated_at = NOW();
        """,
        uid, user.first_name, lang, dob_str, location_label, rasi, deity_mode, freq,
    )

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    reply_markup = build_daily_action_keyboard(today_str, uid, lang)
    summary = (
        f"ॐ <b>AURA</b>  |  <i>Morning Ashirvad Ready</i> 🙏\n"
        f"{DIVIDER}\n\n"
        f"• <b>Language:</b> {html.escape(LANG_NAMES.get(lang, lang))}\n\n"
        f"• <b>Date of Birth:</b> {html.escape(dob_str or 'Not set')}\n\n"
        f"• <b>Locality / City:</b> {html.escape(location_label)}\n\n"
        f"• <b>Rasi:</b> {html.escape(rasi)}\n\n"
        f"Your daily blessing arrives every morning at <b>04:30 AM IST</b>.\n\n"
        f"{SHORT_DISCLAIMER}"
    )
    await query.edit_message_text(summary, reply_markup=reply_markup, parse_mode="HTML")
    context.user_data.clear()
    return ConversationHandler.END


async def open_profile_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    assert db_pool is not None
    row = await db_pool.fetchrow(
        "SELECT first_name, dob, preferred_language FROM subscribers WHERE telegram_id = $1;",
        uid,
    )
    name_val = html.escape(str(row["first_name"] or query.from_user.first_name or "Not set")) if row else html.escape(query.from_user.first_name or "Not set")
    dob_val = html.escape(str(row["dob"] or "Not set")) if row else "Not set"
    lang = (row["preferred_language"] if row and row["preferred_language"] else "en")

    text = (
        f"ॐ <b>AURA</b>  |  <i>User Profile</i>\n"
        f"{DIVIDER}\n\n"
        f"• <b>Name:</b> {name_val}\n\n"
        f"• <b>Date of Birth:</b> {dob_val}\n\n"
        f"Select a profile field below to edit:"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Name", callback_data="editfield:first_name")],
        [InlineKeyboardButton("🎂 Edit Date of Birth", callback_data="editfield:dob")],
        [InlineKeyboardButton(t(lang, "settings_btn"), callback_data="menu:settings")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    return ConversationHandler.END


async def open_settings_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    assert db_pool is not None
    row = await db_pool.fetchrow(
        "SELECT preferred_language, city, rasi, deity_mode, subscribed_12_pillars FROM subscribers WHERE telegram_id = $1;",
        uid,
    )
    lang = (row["preferred_language"] if row and row["preferred_language"] else "en")
    city_val = html.escape(str(row["city"] or "Chennai")) if row else "Chennai"
    rasi_val = html.escape(str(row["rasi"] or "Mesham")) if row else "Mesham"
    deity_val = html.escape(str(row["deity_mode"] or "AUTO")) if row else "AUTO"
    pillars_val = "Subscribed" if (row and row["subscribed_12_pillars"]) else "Not Subscribed"

    text = (
        f"ॐ <b>AURA</b>  |  <i>Preferences &amp; Settings</i>\n"
        f"{DIVIDER}\n\n"
        f"• <b>Language:</b> {html.escape(LANG_NAMES.get(lang, lang))}\n\n"
        f"• <b>Locality / City:</b> {city_val}\n\n"
        f"• <b>Rasi:</b> {rasi_val}\n\n"
        f"• <b>Devotional / Occasion Mode:</b> {deity_val}\n\n"
        f"• <b>12 Pillars Alerts:</b> {pillars_val}\n\n"
        f"Select any setting below to update:"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌐 Language", callback_data="editfield:preferred_language"),
            InlineKeyboardButton("📍 Locality / City", callback_data="editfield:city"),
        ],
        [
            InlineKeyboardButton("✨ Rasi", callback_data="editfield:rasi"),
            InlineKeyboardButton("🪔 Devotional Mode", callback_data="editfield:deity_mode"),
        ],
        [InlineKeyboardButton(t(lang, "profile_btn"), callback_data="menu:profile")],
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    return ConversationHandler.END


async def choose_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    field = query.data.split(":", 1)[1]
    context.user_data["editing_field"] = field

    if field == "preferred_language":
        rows = [
            [InlineKeyboardButton("English", callback_data="editval_lang:en"), InlineKeyboardButton("தமிழ் (Tamil)", callback_data="editval_lang:ta")],
            [InlineKeyboardButton("हिन्दी (Hindi)", callback_data="editval_lang:hi"), InlineKeyboardButton("తెలుగు (Telugu)", callback_data="editval_lang:te")],
            [InlineKeyboardButton("ಕನ್ನಡ (Kannada)", callback_data="editval_lang:kn"), InlineKeyboardButton("മലയാളം (Malayalam)", callback_data="editval_lang:ml")],
        ]
        await query.edit_message_text("Select your new <b>Language</b>:", reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")
        return EDIT_VALUE

    if field == "rasi":
        rasi_rows, row = [], []
        for rasi in RASI_LIST:
            row.append(InlineKeyboardButton(rasi, callback_data=f"editval_rasi:{rasi}"))
            if len(row) == 3:
                rasi_rows.append(row)
                row = []
        if row:
            rasi_rows.append(row)
        await query.edit_message_text("Select your new <b>Rasi</b>:", reply_markup=InlineKeyboardMarkup(rasi_rows), parse_mode="HTML")
        return EDIT_VALUE

    if field == "deity_mode":
        rows = [
            [InlineKeyboardButton("AUTO (Blessing + Occasions)", callback_data="editval_deity:AUTO")],
            [InlineKeyboardButton("DAY_OF_WEEK", callback_data="editval_deity:DAY_OF_WEEK")],
            [InlineKeyboardButton("ALL_OCCASIONS", callback_data="editval_deity:ALL_OCCASIONS")],
        ]
        await query.edit_message_text("Select your <b>Devotional / Occasion Mode</b>:", reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")
        return EDIT_VALUE

    prompts = {
        "first_name": "Enter your updated <b>Name</b>:",
        "dob": "Enter your updated <b>Date of Birth</b> (e.g., <code>15-08-1985</code>):",
        "city": "Enter your updated <b>Locality &amp; City</b> (e.g., <code>Ambattur, Chennai</code> or <code>Chennai</code>):",
    }
    await query.edit_message_text(prompts.get(field, "Enter updated value:"), parse_mode="HTML")
    return EDIT_VALUE


async def save_edited_callback_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    prefix, val = query.data.split(":", 1)
    field = context.user_data.get("editing_field")
    uid = query.from_user.id
    assert db_pool is not None

    if prefix == "editval_lang" or field == "preferred_language":
        await db_pool.execute("UPDATE subscribers SET preferred_language = $1, updated_at = NOW() WHERE telegram_id = $2;", val, uid)
    elif prefix == "editval_rasi" or field == "rasi":
        await db_pool.execute("UPDATE subscribers SET rasi = $1, updated_at = NOW() WHERE telegram_id = $2;", val, uid)
    elif prefix == "editval_deity" or field == "deity_mode":
        await db_pool.execute("UPDATE subscribers SET deity_mode = $1, updated_at = NOW() WHERE telegram_id = $2;", val, uid)

    context.user_data.pop("editing_field", None)
    sub = await db_pool.fetchrow("SELECT preferred_language FROM subscribers WHERE telegram_id = $1;", uid)
    lang = (sub["preferred_language"] if sub and sub["preferred_language"] else "en")
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await query.edit_message_text(
        f"✅ <b>Saved:</b> <code>{html.escape(val)}</code>",
        reply_markup=build_daily_action_keyboard(today_str, uid, lang),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def save_edited_text_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    field = context.user_data.get("editing_field")
    raw_val = (update.message.text or "").strip()
    uid = update.effective_user.id
    assert db_pool is not None

    if field == "dob":
        parsed = normalize_dob(raw_val)
        if not parsed:
            await update.message.reply_text("Please enter a valid Date of Birth (e.g., <code>15-08-1985</code>):", parse_mode="HTML")
            return EDIT_VALUE
        await db_pool.execute("UPDATE subscribers SET dob = $1, updated_at = NOW() WHERE telegram_id = $2;", parsed, uid)
        saved_label = parsed
    elif field == "city":
        loc_val = format_location_input(raw_val)
        await db_pool.execute("UPDATE subscribers SET city = $1, updated_at = NOW() WHERE telegram_id = $2;", loc_val, uid)
        saved_label = loc_val
    else:
        name_val = re.sub(r"\s+", " ", raw_val)[:120]
        if not name_val:
            await update.message.reply_text("Please enter a valid Name:")
            return EDIT_VALUE
        await db_pool.execute("UPDATE subscribers SET first_name = $1, updated_at = NOW() WHERE telegram_id = $2;", name_val, uid)
        saved_label = name_val

    context.user_data.pop("editing_field", None)
    sub = await db_pool.fetchrow("SELECT preferred_language FROM subscribers WHERE telegram_id = $1;", uid)
    lang = (sub["preferred_language"] if sub and sub["preferred_language"] else "en")
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await update.message.reply_text(
        f"✅ <b>Saved:</b> {html.escape(saved_label)}",
        reply_markup=build_daily_action_keyboard(today_str, uid, lang),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cancel_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Action cancelled. Type /start anytime to begin again.")
    return ConversationHandler.END


async def delete_data_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    assert db_pool is not None
    row = await db_pool.fetchrow("SELECT preferred_language FROM subscribers WHERE telegram_id = $1;", uid)
    lang = (row["preferred_language"] if row and row["preferred_language"] else "en")
    await db_pool.execute("DELETE FROM subscribers WHERE telegram_id = $1;", uid)
    await update.message.reply_text(t(lang, "erased"), parse_mode="HTML")


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
        f"📩 <b>AURA Support Update — {html.escape(ticket_id)}</b> ({html.escape(row['category'])})\n\n"
        f"{html.escape(reply_body)}\n\nStatus: <b>Closed</b> ✅"
    )
    await context.bot.send_message(chat_id=row["telegram_id"], text=user_notice, parse_mode="HTML")
    await update.message.reply_text(f"✅ Reply sent to user {row['telegram_id']} and {ticket_id} marked CLOSED.")


async def handle_rating_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    edition_date_str, rating_val, uid = parts[1], int(parts[2]), query.from_user.id
    assert db_pool is not None
    row = await db_pool.fetchrow("SELECT preferred_language FROM subscribers WHERE telegram_id = $1;", uid)
    lang = (row["preferred_language"] if row and row["preferred_language"] else "en")
    try:
        await db_pool.execute(
            """
            INSERT INTO message_ratings (telegram_id, edition_date, rating, rated_at)
            VALUES ($1, $2::date, $3, NOW())
            ON CONFLICT (telegram_id, edition_date) DO UPDATE SET rating = EXCLUDED.rating, rated_at = NOW();
            """,
            uid, edition_date_str, rating_val,
        )
        await query.answer(t(lang, "rate_toast").format(val=rating_val), show_alert=False)
    except Exception:
        await query.answer("Rating recorded!", show_alert=False)


async def handle_other_services_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    assert db_pool is not None
    row = await db_pool.fetchrow("SELECT subscribed_12_pillars, preferred_language FROM subscribers WHERE telegram_id = $1;", uid)
    is_subbed = row["subscribed_12_pillars"] if row else False
    lang = (row["preferred_language"] if row and row["preferred_language"] else "en")
    toggle_txt = t(lang, "unsub_12") if is_subbed else t(lang, "sub_12")
    keyboard = [
        [InlineKeyboardButton(toggle_txt, callback_data="sub:12pillars_toggle")],
        [InlineKeyboardButton("📺 YouTube", url="https://youtube.com"), InlineKeyboardButton("📸 Instagram", url="https://instagram.com")],
        [InlineKeyboardButton("🐦 X (Twitter)", url="https://x.com"), InlineKeyboardButton("💼 LinkedIn", url="https://linkedin.com")],
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
    await query.answer(f"You have {status_txt} AURA 12 Pillars News Alerts!", show_alert=True)


async def handle_translate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split(":")
    target_lang, edition_date_str = parts[1], parts[2]
    assert db_pool is not None
    rows = await db_pool.fetch(
        "SELECT bucket_key, payload_json FROM daily_shared_cache WHERE edition_date = $1::date AND language = $2;",
        edition_date_str, target_lang,
    )
    if not rows:
        rows = await db_pool.fetch(
            "SELECT bucket_key, payload_json FROM daily_shared_cache WHERE edition_date = $1::date AND language = 'en';",
            edition_date_str,
        )
    if not rows:
        await query.answer("English translation unavailable for this edition.", show_alert=True)
        return
    await query.answer("Translated to English", show_alert=False)
    cache = {
        r["bucket_key"]: json.loads(r["payload_json"]) if isinstance(r["payload_json"], str) else r["payload_json"]
        for r in rows
    }
    deity = cache.get("DEITY_DAY_OF_WEEK", {})
    gold = cache.get("GOLD_INR", {})
    quote_block = cache.get("FAMOUS_QUOTE", {})
    translated_txt = (
        f"🌐 <b>AURA — English Translation ({html.escape(edition_date_str)})</b>\n\n"
        f"🪔 <b>{html.escape(str(deity.get('title', 'Daily Blessing')))}</b>\n{html.escape(str(deity.get('slogan', '')))}\n\n"
        f"🪙 <b>Gold &amp; Silver Rates:</b> {html.escape(str(gold.get('board_summary', '')))}\n\n"
        f"✨ <i>\"{html.escape(str(quote_block.get('quote', '')))}\"</i> — {html.escape(str(quote_block.get('author', '')))}\n\n"
        f"{SHORT_DISCLAIMER}"
    )
    await context.bot.send_message(chat_id=query.from_user.id, text=translated_txt, parse_mode="HTML")


async def handle_health_check(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "AURA Web Server", "utc": datetime.now(timezone.utc).isoformat()})


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
    await db_pool.execute(
        """
        INSERT INTO support_tickets (
            ticket_id, telegram_id, preferred_language, category, message_text, status, email_dispatched, created_at
        )
        VALUES ($1, $2, $3, $4, $5, 'OPEN', TRUE, NOW());
        """,
        ticket_id, telegram_id, lang, category, message_text,
    )
    bot = request.app["tg_app"].bot
    ack_text = (
        f"✅ <b>AURA Support Ticket Logged:</b> <code>{html.escape(ticket_id)}</code>\n\n"
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
    await db_pool.execute("ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS dob VARCHAR(20);")
    tg_app = ApplicationBuilder().token(BOT_TOKEN).read_timeout(60).write_timeout(60).connect_timeout(30).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_cmd),
            CallbackQueryHandler(choose_edit_field, pattern=r"^editfield:"),
        ],
        states={
            LANG: [CallbackQueryHandler(set_language_callback, pattern=r"^lang:")],
            DOB: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_dob),
                CallbackQueryHandler(back_to_language_callback, pattern=r"^back:lang$"),
            ],
            LOCATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_location),
                CallbackQueryHandler(back_to_dob_callback, pattern=r"^back:dob$"),
            ],
            RASI: [
                CallbackQueryHandler(set_rasi_callback, pattern=r"^rasi:"),
                CallbackQueryHandler(back_to_location_callback, pattern=r"^back:location$"),
            ],
            EDIT_VALUE: [
                CallbackQueryHandler(save_edited_callback_value, pattern=r"^editval_(lang|rasi|deity):"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_edited_text_value),
            ],
        },
        fallbacks=[
            CommandHandler("start", start_cmd),
            CommandHandler("cancel", cancel_onboarding),
        ],
        allow_reentry=True,
    )

    tg_app.add_handler(conv_handler)
    tg_app.add_handler(CallbackQueryHandler(open_profile_panel, pattern=r"^menu:profile$"))
    tg_app.add_handler(CallbackQueryHandler(open_settings_panel, pattern=r"^menu:settings$"))
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
    print(f"AURA Bot Web Service running on port {PORT}...")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
