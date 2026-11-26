import os
import re
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, date, timezone, timedelta
from typing import Optional

import asyncpg
from aiohttp import web

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
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

UPI_GATEWAY_CHECKOUT_URL = os.environ.get("UPI_GATEWAY_CHECKOUT_URL", "https://example.com/upi")
ADMIN_SUPPORT_CHAT_ID = os.environ.get("ADMIN_SUPPORT_CHAT_ID", "").strip()
WELCOME_VIDEO_PATH = Path(
    os.environ.get("WELCOME_VIDEO_PATH", "assets/welcome_aura_is_here_to_serve_6s.mp4")
)
WELCOME_VIDEO_WIDTH = int(os.environ.get("WELCOME_VIDEO_WIDTH", "1280"))
WELCOME_VIDEO_HEIGHT = int(os.environ.get("WELCOME_VIDEO_HEIGHT", "720"))

IST = timezone(timedelta(hours=5, minutes=30))

# Conversation states
LANG, DOB, LOCATION, RASI, EDIT_VALUE, FEEDBACK_TEXT = range(6)

CARD_HEADER = (
    "<b>ॐ  AURA  |  Daily Morning Grace &amp; Divine Blessings  ॐ</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
)

LANGUAGES = {
    "en": "English",
    "ta": "தமிழ் (Tamil)",
    "hi": "हिन्दी (Hindi)",
    "te": "తెలుగు (Telugu)",
    "kn": "ಕನ್ನಡ (Kannada)",
    "ml": "മലയാളം (Malayalam)",
}

WOW_LABELS = {
    "en": "WoW [Words of Wisdom]",
    "ta": "WoW [ஞான மொழிகள்]",
    "hi": "WoW [ज्ञान की बातें]",
    "te": "WoW [జ్ఞాన వాక్కులు]",
    "kn": "WoW [ಜ್ಞಾನದ ಮಾತುಗಳು]",
    "ml": "WoW [ജ്ഞാനവാക്കുകൾ]",
}

QUOTE_LABELS = {
    "en": "Quote",
    "ta": "பொன்மொழி",
    "hi": "अनमोल वचन",
    "te": "సూక్తి",
    "kn": "ನುಡಿಮುತ್ತು",
    "ml": "സന്ദേശം",
}

BLESSING_WITH_LABELS = {
    "en": "Daily Blessing",
    "ta": "தினசரி ஆசீர்வாதம்",
    "hi": "दैनिक आशीर्वाद",
    "te": "రోజువారీ ఆశీర్వాదం",
    "kn": "ದೈನಂದಿನ ಆಶೀರ್ವಾದ",
    "ml": "ദൈനംദിന അനുഗ്രഹം",
}

GOLD_RATE_LABELS = {
    "en": "Gold Rate",
    "ta": "தங்கம் விலை",
    "hi": "सोना भाव",
    "te": "బంగారం ధర",
    "kn": "ಚಿನ್ನ ದರ",
    "ml": "സ്വർണ്ണ നിരക്ക്",
}

SILVER_RATE_LABELS = {
    "en": "Silver Rate",
    "ta": "வெள்ளி விலை",
    "hi": "चांदी भाव",
    "te": "వెండి ధర",
    "kn": "ಬೆಳ್ಳಿ ದರ",
    "ml": "വെള്ളി നിരക്ക്",
}

LOCALIZED_CARD_DEFAULTS = {
    "en": {
        "deity": "🪔 <b>Daily Blessing:</b> Om Namah Shivaya",
        "wow": "✨ <b>WoW [Words of Wisdom]:</b> Stay steady and focused today.",
        "ausp": "⏰ <b>Auspicious Timing [Plan Your Decisions]:</b> Morning 06:00–07:30 AM",
        "gold": "🟡 <b>Gold Rate ⚪️ Silver Rate [As of {date}]:</b> Updating shortly",
        "weather": "🌦 <b>Weather [Plan Your Day]:</b> Pleasant morning breeze",
        "quote": '🌟 <b>Quote:</b>\n"You have a right to perform your prescribed duty, but never to its fruits." — <i>Bhagavad Gita (2.47)</i>',
    },
    "ta": {
        "deity": "🪔 <b>தினசரி ஆசீர்வாதம்:</b> ஓம் நம சிவாய",
        "wow": "✨ <b>WoW [ஞான மொழிகள்]:</b> இன்று அமைதியுடனும் தெளிவான கவனத்துடனும் செயல்படுங்கள்.",
        "ausp": "⏰ <b>நல்ல நேரம் [உங்கள் முடிவுகளைத் திட்டமிடுங்கள்]:</b> காலை 06:00–07:30 AM",
        "gold": "🟡 <b>தங்கம் விலை ⚪️ வெள்ளி விலை [{date} நிலவரப்படி]:</b> விரைவில் புதுப்பிக்கப்படும்",
        "weather": "🌦 <b>வானிலை [உங்கள் நாளைத் திட்டமிடுங்கள்]:</b> இனிமையான காலை தென்றல்",
        "quote": '🌟 <b>பொன்மொழி:</b>\n"கடமையைச் செய்வதற்கே உனக்கு அதிகாரம் உண்டு; அதன் பலன்களில் ஒருபோதும் இல்லை." — <i>பகவத் கீதை (2.47)</i>',
    },
    "hi": {
        "deity": "🪔 <b>दैनिक आशीर्वाद:</b> ॐ नमः शिवाय",
        "wow": "✨ <b>WoW [ज्ञान की बातें]:</b> आज शांत मन और एकाग्रता के साथ आगे बढ़ें।",
        "ausp": "⏰ <b>शुभ समय [अपने निर्णयों की योजना बनाएं]:</b> प्रातः 06:00–07:30 AM",
        "gold": "🟡 <b>सोना भाव ⚪️ चांदी भाव [{date} तक]:</b> शीघ्र अपडेट हो रहा है",
        "weather": "🌦 <b>मौसम [दिन की योजना]:</b> सुहावनी सुबह की हवा",
        "quote": '🌟 <b>अनमोल वचन:</b>\n"कर्म करने में ही तुम्हारा अधिकार है, उसके फलों में कभी नहीं।" — <i>भगवद्गीता (2.47)</i>',
    },
    "te": {
        "deity": "🪔 <b>రోజువారీ ఆశీర్వాదం:</b> ఓం నమః శివాయ",
        "wow": "✨ <b>WoW [జ్ఞాన వాక్కులు]:</b> నేడు ప్రశాంతంగా మరియు స్పష్టమైన దృష్టితో ముందుకు సాగండి.",
        "ausp": "⏰ <b>శుభ సమయం [మీ నిర్ణయాలను ప్రణాళిక చేయండి]:</b> ఉదయం 06:00–07:30 AM",
        "gold": "🟡 <b>బంగారం ధర ⚪️ వెండి ధర [{date} నాటికి]:</b> త్వరలో నవీకరించబడుతుంది",
        "weather": "🌦 <b>వాతావరణం [రోజు ప్రణాళిక]:</b> ఆహ్లాదకరమైన ఉదయపు గాలి",
        "quote": '🌟 <b>సూక్తి:</b>\n"నీ విధిని నిర్వర్తించే హక్కు మాత్రమే నీకు ఉంది, ఫలితాలపై ఎన్నడూ లేదు." — <i>భగవద్గీత (2.47)</i>',
    },
    "kn": {
        "deity": "🪔 <b>ದೈನಂದಿನ ಆಶೀರ್ವಾದ:</b> ಓಂ ನಮಃ ಶಿವಾಯ",
        "wow": "✨ <b>WoW [ಜ್ಞಾನದ ಮಾತುಗಳು]:</b> ಇಂದು ಶಾಂತವಾಗಿ ಮತ್ತು ಸ್ಪಷ್ಟ ಗಮನದಿಂದ ಮುನ್ನಡೆಯಿರಿ.",
        "ausp": "⏰ <b>ಶುಭ ಸಮಯ [ನಿಮ್ಮ ನಿರ್ಧಾರಗಳನ್ನು ಯೋಜಿಸಿ]:</b> ಬೆಳಿಗ್ಗೆ 06:00–07:30 AM",
        "gold": "🟡 <b>ಚಿನ್ನ ದರ ⚪️ ಬೆಳ್ಳಿ ದರ [{date} ರಂತೆ]:</b> ಶೀಘ್ರದಲ್ಲೇ ನವೀಕರಿಸಲಾಗುವುದು",
        "weather": "🌦 <b>ಹವಾಮಾನ [ದಿನದ ಯೋಜನೆ]:</b> ಆಹ್ಲಾದಕರ ಮುಂಜಾನೆಯ ಗಾಳಿ",
        "quote": '🌟 <b>ನುಡಿಮುತ್ತು:</b>\n"ನಿನ್ನ ಕರ್ತವ್ಯವನ್ನು ಮಾಡಲು ಮಾತ್ರ ನಿನಗೆ ಹಕ್ಕಿದೆ, ಅದರ ಫಲಗಳ ಮೇಲೆ ಎಂದಿಗೂ ಇಲ್ಲ." — <i>ಭಗವದ್ಗೀತೆ (2.47)</i>',
    },
    "ml": {
        "deity": "🪔 <b>ദൈനംദിന അനുഗ്രഹം:</b> ഓം നമഃ ശിവായ",
        "wow": "✨ <b>WoW [ജ്ഞാനവാക്കുകൾ]:</b> ഇന്ന് ശാന്തമായും വ്യക്തമായ ശ്രദ്ധയോടെയും മുന്നോട്ട് പോകുക.",
        "ausp": "⏰ <b>ശുഭ സമയം [തീരുമാനങ്ങൾ ആസൂത്രണം ചെയ്യുക]:</b> രാവിലെ 06:00–07:30 AM",
        "gold": "🟡 <b>സ്വർണ്ണ നിരക്ക് ⚪️ വെള്ളി നിരക്ക് [{date} പ്രകാരം]:</b> ഉടൻ അപ്‌ഡേറ്റ് ചെയ്യുന്നതാണ്",
        "weather": "🌦 <b>കാലാവസ്ഥ [ദിവസ ആസൂത്രണം]:</b> പ്രസന്നമായ പ്രഭാത കാറ്റ്",
        "quote": '🌟 <b>സന്ദേശം:</b>\n"കർമ്മം ചെയ്യാൻ മാത്രമേ നിനക്ക് അധികാരമുള്ളൂ, അതിന്റെ ഫലങ്ങളിലൊരിക്കലുമില്ല." — <i>ഭഗവദ്ഗീത (2.47)</i>',
    },
}

RASIS = [
    ("mesham", "Mesham", {"en": "Mesham", "ta": "மேஷம் (Mesham)", "hi": "मेष (Mesham)", "te": "మేషం (Mesham)", "kn": "ಮೇಷ (Mesham)", "ml": "മേടം (Mesham)"}),
    ("rishabam", "Rishabam", {"en": "Rishabam", "ta": "ரிஷபம் (Rishabam)", "hi": "वृषभ (Rishabam)", "te": "వృషభం (Rishabam)", "kn": "ವೃಷಭ (Rishabam)", "ml": "ഇടവം (Rishabam)"}),
    ("mithunam", "Mithunam", {"en": "Mithunam", "ta": "மிதுனம் (Mithunam)", "hi": "मिथुन (Mithunam)", "te": "మిథునం (Mithunam)", "kn": "ಮಿಥುನ (Mithunam)", "ml": "മിഥുനം (Mithunam)"}),
    ("kadagam", "Kadagam", {"en": "Kadagam", "ta": "கடகம் (Kadagam)", "hi": "कर्क (Kadagam)", "te": "కర్కాటకం (Kadagam)", "kn": "ಕಟಕ (Kadagam)", "ml": "കർക്കിടകം (Kadagam)"}),
    ("simmam", "Simmam", {"en": "Simmam", "ta": "சிம்மம் (Simmam)", "hi": "सिंह (Simmam)", "te": "సింహం (Simmam)", "kn": "ಸಿಂಹ (Simmam)", "ml": "ചിങ്ങം (Simmam)"}),
    ("kanni", "Kanni", {"en": "Kanni", "ta": "கன்னி (Kanni)", "hi": "कन्या (Kanni)", "te": "కన్య (Kanni)", "kn": "ಕನ್ಯಾ (Kanni)", "ml": "കന്നി (Kanni)"}),
    ("thulam", "Thulam", {"en": "Thulam", "ta": "துலாம் (Thulam)", "hi": "तुला (Thulam)", "te": "తుల (Thulam)", "kn": "ತುಲಾ (Thulam)", "ml": "തുലാം (Thulam)"}),
    ("vrischikam", "Vrischikam", {"en": "Vrischikam", "ta": "விருச்சிகம் (Vrischikam)", "hi": "वृश्चिक (Vrischikam)", "te": "వృశ్చికం (Vrischikam)", "kn": "ವೃಶ್ಚಿಕ (Vrischikam)", "ml": "വൃശ്ചികം (Vrischikam)"}),
    ("dhanusu", "Dhanusu", {"en": "Dhanusu", "ta": "தனுசு (Dhanusu)", "hi": "धनु (Dhanusu)", "te": "ధనుస్సు (Dhanusu)", "kn": "ಧನುಸ್ಸು (Dhanusu)", "ml": "ധനു (Dhanusu)"}),
    ("magaram", "Magaram", {"en": "Magaram", "ta": "மகரம் (Magaram)", "hi": "मकर (Magaram)", "te": "మకరం (Magaram)", "kn": "ಮಕರ (Magaram)", "ml": "മകരം (Magaram)"}),
    ("kumbam", "Kumbam", {"en": "Kumbam", "ta": "கும்பம் (Kumbam)", "hi": "कुंभ (Kumbam)", "te": "కుంభం (Kumbam)", "kn": "ಕುಂಭ (Kumbam)", "ml": "കുംഭം (Kumbam)"}),
    ("meenam", "Meenam", {"en": "Meenam", "ta": "மீனம் (Meenam)", "hi": "मीन (Meenam)", "te": "మీనం (Meenam)", "kn": "ಮೀನ (Meenam)", "ml": "മീനം (Meenam)"}),
]

WELCOME_COPY = {
    "en": {
        "greeting": "Namaskaram, <b>{name}</b> 🙏",
        "schedule": "Every morning at <b>04:30 AM IST</b>, receive one calm and divine message to start your day with <b>Ashirvad:</b>",
        "b1": "• 🪔 {blessing_with} 🛕 Temple &amp; Occasion Alerts",
        "b2": "• ✨ {wow}",
        "b3": "• ⏰ Auspicious Timing [Plan Your Decisions]",
        "b4": "• 🟡 {gold_rate} ⚪️ {silver_rate}",
        "b5": "• 🌦 Weather [Plan Your Day]",
        "b6": "• 🌟 {quote}",
        "step1": "<b>Step 1 of 3</b> — Enter your Date of Birth (e.g., <code>15-08-1985</code>):",
        "invalid_dob": "Please enter a valid Date of Birth in <code>DD-MM-YYYY</code> format (e.g., <code>15-08-1985</code>):",
        "step2": (
            "<b>Step 2 of 3</b> — Enter your Locality &amp; City (or just your City):\n"
            "<i>Example: <code>Ambattur, Chennai</code> or <code>Adyar, Chennai</code> (or <code>Chennai</code>).\n"
            "Why? Adding your locality gives sharper local weather &amp; rain updates.</i>"
        ),
        "invalid_loc": "Please enter your Locality &amp; City (e.g., <code>Ambattur, Chennai</code> or <code>Adyar, Chennai</code>):",
        "step3": "<b>Step 3 of 3</b> — Select your Zodiac / Rasi:",
        "back_lang": "← Back to Language",
        "back_dob": "← Back to Date of Birth",
        "back_loc": "← Back to Locality / City",
        "back_card": "← Back to Card",
        "back_profile": "← Back to Profile",
        "confirmed_title": "🙏 <b>Subscription Confirmed — Ashirvad Active</b>",
        "lbl_name": "Name",
        "lbl_lang": "Language",
        "lbl_dob": "Date of Birth",
        "lbl_loc": "Locality / City",
        "lbl_rasi": "Zodiac / Rasi",
        "lbl_time": "Daily Delivery: <b>04:30 AM IST</b>",
        "btn_sample": "📨 Send Today's Card Now",
        "btn_profile": "👤 Profile",
        "btn_other": "📣 Other Services",
        "btn_12pillars": "🏛️ 12 Pillars View",
        "btn_pay": "🛒 Shop",
        "btn_help": "💬 Help & Feedback",
        "btn_translate": "🌐 Translate [ENG]",
        "btn_close_translation": "✕ Close Translation",
        "btn_privacy": "🔒 Privacy & Data (DPDPA)",
        "btn_delete": "🗑️ Delete My Data (DPDPA)",
        "btn_confirm_delete": "⚠️ Confirm Permanent Erasure",
        "btn_edit_name": "✏️ Edit Name",
        "btn_edit_dob": "🎂 Edit Date of Birth",
        "btn_edit_lang": "🌐 Edit Language",
        "btn_edit_loc": "📍 Edit Locality / City",
        "btn_edit_rasi": "✨ Edit Rasi",
        "profile_title": "👤 <b>Your Profile &amp; Preferences</b>",
        "other_title": "📣 <b>Other Services</b>",
        "other_body": "• Daily Panchang, Rasi, Gold Rate / Silver Rate &amp; Local Weather telemetry.\n• Tap below to return to your daily card.",
        "help_title": "💬 <b>Help &amp; Feedback</b>",
        "help_prompt": "Type your feedback, question, or support request right here in chat and send it.",
        "help_received": "🙏 <b>Thank you!</b> Your message has been received and logged for our team.",
        "dpdpa_title": "🔒 <b>Privacy &amp; Data (DPDPA 2023)</b>",
        "dpdpa_body": (
            "• <b>Data Stored:</b> Name, Preferred Language, Date of Birth, Locality/City, Rasi, and any support messages you send.\n"
            "• <b>Purpose:</b> Personalizing your daily 04:30 AM IST AURA card and responding to support requests.\n"
            "• <b>Your Rights:</b> Edit details anytime in Profile, or erase all records permanently via <b>Delete My Data (DPDPA)</b> or /delete_data."
        ),
        "confirm_delete_body": "⚠️ <b>Confirm Data Deletion (DPDPA 2023):</b>\nThis permanently removes your saved profile, preferences, and feedback records.",
        "erased_msg": "🗑️ Your profile, preferences, and records have been permanently erased under DPDPA 2023. Tap /start anytime to begin again.",
        "saved_msg": "✅ Updated: <b>{val}</b>",
    },
    "ta": {
        "greeting": "நமஸ்காரம், <b>{name}</b> 🙏",
        "schedule": "தினமும் காலை <b>04:30 AM IST</b> மணிக்கு, உங்கள் நாளை அமைதியுடனும் தெய்வீக அருளுடனும் தொடங்க <b>ஆசீர்வாதத்துடன்</b> ஒரு தெய்வீகச் செய்தி:",
        "b1": "• 🪔 {blessing_with} 🛕 கோவில் &amp; விசேஷ அறிவிப்புகள்",
        "b2": "• ✨ {wow}",
        "b3": "• ⏰ நல்ல நேரம் [உங்கள் முடிவுகளைத் திட்டமிடுங்கள்]",
        "b4": "• 🟡 {gold_rate} ⚪️ {silver_rate}",
        "b5": "• 🌦 வானிலை [உங்கள் நாளைத் திட்டமிடுங்கள்]",
        "b6": "• 🌟 {quote}",
        "step1": "<b>படி 1 / 3</b> — உங்கள் பிறந்த தேதியை உள்ளிடவும் (உதா: <code>15-08-1985</code>):",
        "invalid_dob": "சரியான பிறந்த தேதியை <code>DD-MM-YYYY</code> வடிவில் உள்ளிடவும் (உதா: <code>15-08-1985</code>):",
        "step2": (
            "<b>படி 2 / 3</b> — உங்கள் பகுதி மற்றும் நகரத்தை உள்ளிடவும் (அல்லது நகரம் மட்டும்):\n"
            "<i>உதாரணம்: <code>Ambattur, Chennai</code> அல்லது <code>Adyar, Chennai</code> (அல்லது <code>Chennai</code>).\n"
            "ஏன்? பகுதியைச் சேர்த்தால் அருகிலுள்ள மழை மற்றும் வானிலை தகவல் துல்லியமாக இருக்கும்.</i>"
        ),
        "invalid_loc": "உங்கள் பகுதி மற்றும் நகரத்தை உள்ளிடவும் (உதா: <code>Ambattur, Chennai</code> அல்லது <code>Adyar, Chennai</code>):",
        "step3": "<b>படி 3 / 3</b> — உங்கள் ராசியைத் தேர்ந்தெடுக்கவும்:",
        "back_lang": "← மொழிக்குத் திரும்புக",
        "back_dob": "← பிறந்த தேதிக்குத் திரும்புக",
        "back_loc": "← பகுதி / நகரத்திற்குத் திரும்புக",
        "back_card": "← அட்டைக்குத் திரும்புக",
        "back_profile": "← சுயவிவரத்திற்குத் திரும்புக",
        "confirmed_title": "🙏 <b>பதிவு உறுதி செய்யப்பட்டது — ஆசீர்வாதம் செயலில் உள்ளது</b>",
        "lbl_name": "பெயர்",
        "lbl_lang": "மொழி",
        "lbl_dob": "பிறந்த தேதி",
        "lbl_loc": "பகுதி / நகரம்",
        "lbl_rasi": "ராசி",
        "lbl_time": "Daily Delivery: <b>04:30 AM IST</b>",
        "btn_sample": "📨 இன்றைய அட்டையை அனுப்புக",
        "btn_profile": "👤 சுயவிவரம்",
        "btn_other": "📣 மற்ற சேவைகள்",
        "btn_12pillars": "🏛️ 12 தூண்கள் பார்வை",
        "btn_pay": "🛒 Shop",
        "btn_help": "💬 உதவி & கருத்து",
        "btn_translate": "🌐 Translate [ENG]",
        "btn_close_translation": "✕ Close Translation",
        "btn_privacy": "🔒 தனியுரிமை & தரவு (DPDPA)",
        "btn_delete": "🗑️ என் தரவை நீக்கு (DPDPA)",
        "btn_confirm_delete": "⚠️ நிரந்தர நீக்கத்தை உறுதி செய்க",
        "btn_edit_name": "✏️ பெயரை மாற்றுக",
        "btn_edit_dob": "🎂 பிறந்த தேதியை மாற்றுக",
        "btn_edit_lang": "🌐 மொழியை மாற்றுக",
        "btn_edit_loc": "📍 பகுதி / நகரத்தை மாற்றுக",
        "btn_edit_rasi": "✨ ராசியை மாற்றுக",
        "profile_title": "👤 <b>உங்கள் சுயவிவரம் &amp; விருப்பங்கள்</b>",
        "other_title": "📣 <b>மற்ற சேவைகள்</b>",
        "other_body": "• தினசரி பஞ்சாங்கம், ராசி, தங்கம் விலை / வெள்ளி விலை &amp; உள்ளூர் வானிலை விவரங்கள்.\n• அட்டைக்குத் திரும்ப கீழே உள்ள பொத்தானைத் தட்டவும்.",
        "help_title": "💬 <b>உதவி &amp; கருத்து</b>",
        "help_prompt": "உங்கள் கருத்து, கேள்வி அல்லது உதவி கோரிக்கையை இங்கே நேரடியாக தட்டச்சு செய்து அனுப்பவும்.",
        "help_received": "🙏 <b>நன்றி!</b> உங்கள் செய்தி பெறப்பட்டு எங்கள் குழுவிற்காகப் பதிவு செய்யப்பட்டுள்ளது.",
        "dpdpa_title": "🔒 <b>தனியுரிமை &amp; தரவு (DPDPA 2023)</b>",
        "dpdpa_body": (
            "• <b>சேமிக்கப்படும் விவரங்கள்:</b> பெயர், விருப்ப மொழி, பிறந்த தேதி, பகுதி/நகரம், ராசி மற்றும் நீங்கள் அனுப்பும் கருத்துகள்.\n"
            "• <b>நோக்கம்:</b> காலை 04:30 AM IST AURA செய்தியைத் தனிப்பயனாக்கவும் உதவி வழங்கவும்.\n"
            "• <b>உங்கள் உரிமை:</b> சுயவிவரத்தில் விவரங்களை மாற்றலாம்; <b>என் தரவை நீக்கு (DPDPA)</b> அல்லது /delete_data மூலம் நிரந்தரமாக நீக்கலாம்."
        ),
        "confirm_delete_body": "⚠️ <b>தரவு நீக்க உறுதி (DPDPA 2023):</b>\nஉங்கள் சுயவிவரம், விருப்பங்கள் மற்றும் பதிவுகள் நிரந்தரமாக நீக்கப்படும்.",
        "erased_msg": "🗑️ DPDPA 2023 விதிகளின்படி உங்கள் விவரங்கள் நிரந்தரமாக நீக்கப்பட்டன. மீண்டும் தொடங்க /start தட்டவும்.",
        "saved_msg": "✅ புதுப்பிக்கப்பட்டது: <b>{val}</b>",
    },
    "hi": {
        "greeting": "नमस्कार, <b>{name}</b> 🙏",
        "schedule": "हर सुबह <b>04:30 AM IST</b> पर, अपने दिन की शांत और दिव्य शुरुआत के लिए <b>आशीर्वाद</b> के साथ एक पावन संदेश प्राप्त करें:",
        "b1": "• 🪔 {blessing_with} 🛕 मंदिर व विशेष पर्व अलर्ट",
        "b2": "• ✨ {wow}",
        "b3": "• ⏰ शुभ समय [अपने निर्णयों की योजना बनाएं]",
        "b4": "• 🟡 {gold_rate} ⚪️ {silver_rate}",
        "b5": "• 🌦 मौसम [दिन की योजना]",
        "b6": "• 🌟 {quote}",
        "step1": "<b>चरण 1 / 3</b> — अपनी जन्म तिथि दर्ज करें (उदा: <code>15-08-1985</code>):",
        "invalid_dob": "कृपया <code>DD-MM-YYYY</code> प्रारूप में मान्य जन्म तिथि दर्ज करें (उदा: <code>15-08-1985</code>):",
        "step2": (
            "<b>चरण 2 / 3</b> — अपना क्षेत्र और शहर दर्ज करें (या केवल शहर):\n"
            "<i>उदाहरण: <code>Ambattur, Chennai</code> या <code>Adyar, Chennai</code> (या <code>Chennai</code>).\n"
            "क्यों? क्षेत्र जोड़ने से आपके इलाके के अनुसार मौसम की जानकारी अधिक सटीक मिलती है।</i>"
        ),
        "invalid_loc": "कृपया अपना क्षेत्र और शहर दर्ज करें (उदा: <code>Ambattur, Chennai</code> या <code>Adyar, Chennai</code>):",
        "step3": "<b>चरण 3 / 3</b> — अपनी राशि चुनें:",
        "back_lang": "← भाषा पर वापस जाएं",
        "back_dob": "← जन्म तिथि पर वापस जाएं",
        "back_loc": "← क्षेत्र / शहर पर वापस जाएं",
        "back_card": "← कार्ड पर वापस जाएं",
        "back_profile": "← प्रोफ़ाइल पर वापस जाएं",
        "confirmed_title": "🙏 <b>सदस्यता पुष्टि — आशीर्वाद सक्रिय</b>",
        "lbl_name": "नाम",
        "lbl_lang": "भाषा",
        "lbl_dob": "जन्म तिथि",
        "lbl_loc": "क्षेत्र / शहर",
        "lbl_rasi": "राशि",
        "lbl_time": "Daily Delivery: <b>04:30 AM IST</b>",
        "btn_sample": "📨 आज का कार्ड अभी भेजें",
        "btn_profile": "👤 प्रोफ़ाइल",
        "btn_other": "📣 अन्य सेवाएं",
        "btn_12pillars": "🏛️ 12 पिलर्स दृश्य",
        "btn_pay": "🛒 Shop",
        "btn_help": "💬 सहायता व प्रतिक्रिया",
        "btn_translate": "🌐 Translate [ENG]",
        "btn_close_translation": "✕ Close Translation",
        "btn_privacy": "🔒 गोपनीयता व डेटा (DPDPA)",
        "btn_delete": "🗑️ मेरा डेटा हटाएं (DPDPA)",
        "btn_confirm_delete": "⚠️ स्थायी रूप से हटाने की पुष्टि करें",
        "btn_edit_name": "✏️ नाम बदलें",
        "btn_edit_dob": "🎂 जन्म तिथि बदलें",
        "btn_edit_lang": "🌐 भाषा बदलें",
        "btn_edit_loc": "📍 क्षेत्र / शहर बदलें",
        "btn_edit_rasi": "✨ राशि बदलें",
        "profile_title": "👤 <b>आपकी प्रोफ़ाइल व प्राथमिकताएं</b>",
        "other_title": "📣 <b>अन्य सेवाएं</b>",
        "other_body": "• दैनिक पंचांग, राशि, सोना भाव / चांदी भाव और स्थानीय मौसम जानकारी।",
        "help_title": "💬 <b>सहायता व प्रतिक्रिया</b>",
        "help_prompt": "अपनी प्रतिक्रिया, प्रश्न या सहायता अनुरोध यहीं चैट में टाइप करके भेजें।",
        "help_received": "🙏 <b>धन्यवाद!</b> आपका संदेश प्राप्त हो गया है और हमारी टीम के लिए दर्ज कर लिया गया है।",
        "dpdpa_title": "🔒 <b>गोपनीयता व डेटा (DPDPA 2023)</b>",
        "dpdpa_body": (
            "• <b>संग्रहीत विवरण:</b> नाम, भाषा, जन्म तिथि, क्षेत्र/शहर, राशि और आपके सहायता संदेश।\n"
            "• <b>उद्देश्य:</b> प्रातः 04:30 AM IST AURA संदेश को व्यक्तिगत बनाने और सहायता के लिए।\n"
            "• <b>आपके अधिकार:</b> प्रोफ़ाइल में विवरण बदलें या <b>मेरा डेटा हटाएं (DPDPA)</b> / /delete_data से स्थायी रूप से हटाएं।"
        ),
        "confirm_delete_body": "⚠️ <b>डेटा हटाने की पुष्टि (DPDPA 2023):</b>\nआपकी प्रोफ़ाइल, प्राथमिकताएं और रिकॉर्ड स्थायी रूप से हटा दिए जाएंगे।",
        "erased_msg": "🗑️ DPDPA 2023 के तहत आपका डेटा स्थायी रूप से हटा दिया गया है। दोबारा शुरू करने के लिए /start भेजें।",
        "saved_msg": "✅ सहेजा गया: <b>{val}</b>",
    },
    "te": {
        "greeting": "నమస్కారం, <b>{name}</b> 🙏",
        "schedule": "ప్రతిరోజూ ఉదయం <b>04:30 AM IST</b> గంటలకు, మీ రోజును ప్రశాంతంగా మరియు దైవికంగా ప్రారంభించడానికి <b>ఆశీర్వాదంతో</b> ఒక దివ్య సందేశం:",
        "b1": "• 🪔 {blessing_with} 🛕 ఆలయ &amp; ప్రత్యేక విశేషాలు",
        "b2": "• ✨ {wow}",
        "b3": "• ⏰ శుభ సమయం [మీ నిర్ణయాలను ప్రణాళిక చేయండి]",
        "b4": "• 🟡 {gold_rate} ⚪️ {silver_rate}",
        "b5": "• 🌦 వాతావరణం [రోజు ప్రణాళిక]",
        "b6": "• 🌟 {quote}",
        "step1": "<b>దశ 1 / 3</b> — మీ పుట్టిన తేదీని నమోదు చేయండి (ఉదా: <code>15-08-1985</code>):",
        "invalid_dob": "దయచేసి <code>DD-MM-YYYY</code> రూపంలో సరైన పుట్టిన తేదీని నమోదు చేయండి (ఉదా: <code>15-08-1985</code>):",
        "step2": (
            "<b>దశ 2 / 3</b> — మీ ప్రాంతం మరియు నగరాన్ని నమోదు చేయండి (లేదా నగరం మాత్రమే):\n"
            "<i>ఉదాహరణ: <code>Ambattur, Chennai</code> లేదా <code>Adyar, Chennai</code> (లేదా <code>Chennai</code>).\n"
            "ఎందుకు? ప్రాంతం చేరిస్తే స్థానిక వాతావరణ &amp; వర్ష సమాచారం మరింత ఖచ్చితంగా ఉంటుంది.</i>"
        ),
        "invalid_loc": "దయచేసి మీ ప్రాంతం మరియు నగరాన్ని నమోదు చేయండి (ఉదా: <code>Ambattur, Chennai</code> లేదా <code>Adyar, Chennai</code>):",
        "step3": "<b>దశ 3 / 3</b> — మీ రాశిని ఎంచుకోండి:",
        "back_lang": "← భాషకు తిరిగి వెళ్ళండి",
        "back_dob": "← పుట్టిన తేదీకి తిరిగి వెళ్ళండి",
        "back_loc": "← ప్రాంతం / నగరానికి తిరిగి వెళ్ళండి",
        "back_card": "← కార్డ్‌కి తిరిగి వెళ్ళండి",
        "back_profile": "← ప్రొఫైల్‌కి తిరిగి వెళ్ళండి",
        "confirmed_title": "🙏 <b>సబ్‌స్క్రిప్షన్ నిర్ధారించబడింది — ఆశీర్వాదం యాక్టివ్</b>",
        "lbl_name": "పేరు",
        "lbl_lang": "భాష",
        "lbl_dob": "పుట్టిన తేదీ",
        "lbl_loc": "ప్రాంతం / నగరం",
        "lbl_rasi": "రాశి",
        "lbl_time": "Daily Delivery: <b>04:30 AM IST</b>",
        "btn_sample": "📨 నేటి కార్డ్ ఇప్పుడే పంపండి",
        "btn_profile": "👤 ప్రొఫైల్",
        "btn_other": "📣 ఇతర సేవలు",
        "btn_12pillars": "🏛️ 12 పిల్లర్స్ వీక్షణ",
        "btn_pay": "🛒 Shop",
        "btn_help": "💬 సహాయం & అభిప్రాయం",
        "btn_translate": "🌐 Translate [ENG]",
        "btn_close_translation": "✕ Close Translation",
        "btn_privacy": "🔒 గోప్యత & డేటా (DPDPA)",
        "btn_delete": "🗑️ నా డేటా తొలగించండి (DPDPA)",
        "btn_confirm_delete": "⚠️ శాశ్వత తొలగింపును నిర్ధారించండి",
        "btn_edit_name": "✏️ పేరు మార్చండి",
        "btn_edit_dob": "🎂 పుట్టిన తేదీ మార్చండి",
        "btn_edit_lang": "🌐 భాష మార్చండి",
        "btn_edit_loc": "📍 ప్రాంతం / నగరం మార్చండి",
        "btn_edit_rasi": "✨ రాశి మార్చండి",
        "profile_title": "👤 <b>మీ ప్రొఫైల్ &amp; ప్రాధాన్యతలు</b>",
        "other_title": "📣 <b>ఇతర సేవలు</b>",
        "other_body": "• రోజువారీ పంచాంగం, రాశి, బంగారం ధర / వెండి ధర &amp; స్థానిక వాతావరణ సమాచారం.",
        "help_title": "💬 <b>సహాయం &amp; అభిప్రాయం</b>",
        "help_prompt": "మీ అభిప్రాయం, ప్రశ్న లేదా సహాయ అభ్యర్థనను ఇక్కడే చాట్‌లో టైప్ చేసి పంపండి.",
        "help_received": "🙏 <b>ధన్యవాదాలు!</b> మీ సందేశం అందింది మరియు మా బృందం కోసం నమోదు చేయబడింది.",
        "dpdpa_title": "🔒 <b>గోప్యత &amp; డేటా (DPDPA 2023)</b>",
        "dpdpa_body": (
            "• <b>నిల్వ చేసే వివరాలు:</b> పేరు, భాష, పుట్టిన తేదీ, ప్రాంతం/నగరం, రాశి మరియు మీ సహాయ సందేశాలు.\n"
            "• <b>ఉద్దేశం:</b> ఉదయం 04:30 AM IST AURA సందేశాన్ని వ్యక్తిగతీకరించడానికి మరియు సహాయం కోసం.\n"
            "• <b>మీ హక్కులు:</b> ప్రొఫైల్‌లో మార్చవచ్చు లేదా <b>నా డేటా తొలగించండి (DPDPA)</b> / /delete_data ద్వారా శాశ్వతంగా తొలగించవచ్చు."
        ),
        "confirm_delete_body": "⚠️ <b>డేటా తొలగింపు నిర్ధారణ (DPDPA 2023):</b>\nమీ ప్రొఫైల్, ప్రాధాన్యతలు మరియు రికార్డులు శాశ్వతంగా తొలగించబడతాయి.",
        "erased_msg": "🗑️ DPDPA 2023 ప్రకారం మీ డేటా శాశ్వతంగా తొలగించబడింది. మళ్లీ ప్రారంభించడానికి /start నొక్కండి.",
        "saved_msg": "✅ నవీకరించబడింది: <b>{val}</b>",
    },
    "kn": {
        "greeting": "ನಮಸ್ಕಾರ, <b>{name}</b> 🙏",
        "schedule": "ಪ್ರತಿದಿನ ಬೆಳಿಗ್ಗೆ <b>04:30 AM IST</b> ಗಂಟೆಗೆ, ನಿಮ್ಮ ದಿನವನ್ನು ಶಾಂತವಾಗಿ ಮತ್ತು ದೈವಿಕವಾಗಿ ಆರಂಭಿಸಲು <b>ಆಶೀರ್ವಾದದೊಂದಿಗೆ</b> ಒಂದು ದಿವ್ಯ ಸಂದೇಶ:",
        "b1": "• 🪔 {blessing_with} 🛕 ದೇವಾಲಯ &amp; ವಿಶೇಷ ಮಾಹಿತಿ",
        "b2": "• ✨ {wow}",
        "b3": "• ⏰ ಶುಭ ಸಮಯ [ನಿಮ್ಮ ನಿರ್ಧಾರಗಳನ್ನು ಯೋಜಿಸಿ]",
        "b4": "• 🟡 {gold_rate} ⚪️ {silver_rate}",
        "b5": "• 🌦 ಹವಾಮಾನ [ದಿನದ ಯೋಜನೆ]",
        "b6": "• 🌟 {quote}",
        "step1": "<b>ಹಂತ 1 / 3</b> — ನಿಮ್ಮ ಜನ್ಮ ದಿನಾಂಕವನ್ನು ನಮೂದಿಸಿ (ಉದಾ: <code>15-08-1985</code>):",
        "invalid_dob": "ದಯವಿಟ್ಟು <code>DD-MM-YYYY</code> ನಮೂನೆಯಲ್ಲಿ ಸರಿಯಾದ ಜನ್ಮ ದಿನಾಂಕವನ್ನು ನಮೂದಿಸಿ (ಉದಾ: <code>15-08-1985</code>):",
        "step2": (
            "<b>ಹಂತ 2 / 3</b> — ನಿಮ್ಮ ಪ್ರದೇಶ ಮತ್ತು ನಗರವನ್ನು ನಮೂದಿಸಿ (ಅಥವಾ ನಗರ ಮಾತ್ರ):\n"
            "<i>ಉದಾಹರಣೆ: <code>Ambattur, Chennai</code> ಅಥವಾ <code>Adyar, Chennai</code> (ಅಥವಾ <code>Chennai</code>).\n"
            "ಏಕೆ? ಪ್ರದೇಶ ಸೇರಿಸಿದರೆ ಸ್ಥಳೀಯ ಹವಾಮಾನ ಮತ್ತು ಮಳೆ ಮಾಹಿತಿ ಹೆಚ್ಚು ನಿಖರವಾಗಿರುತ್ತದೆ.</i>"
        ),
        "invalid_loc": "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಪ್ರದೇಶ ಮತ್ತು ನಗರವನ್ನು ನಮೂದಿಸಿ (ಉದಾ: <code>Ambattur, Chennai</code> ಅಥವಾ <code>Adyar, Chennai</code>):",
        "step3": "<b>ಹಂತ 3 / 3</b> — ನಿಮ್ಮ ರಾಶಿಯನ್ನು ಆಯ್ಕೆಮಾಡಿ:",
        "back_lang": "← ಭಾಷೆಗೆ ಹಿಂತಿರುಗಿ",
        "back_dob": "← ಜನ್ಮ ದಿನಾಂಕಕ್ಕೆ ಹಿಂತಿರುಗಿ",
        "back_loc": "← ಪ್ರದೇಶ / ನಗರಕ್ಕೆ ಹಿಂತಿರುಗಿ",
        "back_card": "← ಕಾರ್ಡ್‌ಗೆ ಹಿಂತಿರುಗಿ",
        "back_profile": "← ಪ್ರೊಫೈಲ್‌ಗೆ ಹಿಂತಿರುಗಿ",
        "confirmed_title": "🙏 <b>ಚಂದಾದಾರಿಕೆ ದೃಢೀಕೃತ — ಆಶೀರ್ವಾದ ಸಕ್ರಿಯ</b>",
        "lbl_name": "ಹೆಸರು",
        "lbl_lang": "ಭಾಷೆ",
        "lbl_dob": "ಜನ್ಮ ದಿನಾಂಕ",
        "lbl_loc": "ಪ್ರದೇಶ / ನಗರ",
        "lbl_rasi": "ರಾಶಿ",
        "lbl_time": "Daily Delivery: <b>04:30 AM IST</b>",
        "btn_sample": "📨 ಇಂದಿನ ಕಾರ್ಡ್ ಈಗ ಕಳುಹಿಸಿ",
        "btn_profile": "👤 ಪ್ರೊಫೈಲ್",
        "btn_other": "📣 ಇತರೆ ಸೇವೆಗಳು",
        "btn_12pillars": "🏛️ 12 ಪಿಲ್ಲರ್ಸ್ ವೀಕ್ಷಣೆ",
        "btn_pay": "🛒 Shop",
        "btn_help": "💬 ಬೆಂಬಲ & ಪ್ರತಿಕ್ರಿಯೆ",
        "btn_translate": "🌐 Translate [ENG]",
        "btn_close_translation": "✕ Close Translation",
        "btn_privacy": "🔒 ಗೌಪ್ಯತೆ ಮತ್ತು ಡೇಟಾ (DPDPA)",
        "btn_delete": "🗑️ ನನ್ನ ಡೇಟಾ ಅಳಿಸಿ (DPDPA)",
        "btn_confirm_delete": "⚠️ ಶಾಶ್ವತ ಅಳಿಸುವಿಕೆಯನ್ನು ದೃಢೀಕರಿಸಿ",
        "btn_edit_name": "✏️ ಹೆಸರು ಬದಲಿಸಿ",
        "btn_edit_dob": "🎂 ಜನ್ಮ ದಿನಾಂಕ ಬದಲಿಸಿ",
        "btn_edit_lang": "🌐 ಭಾಷೆ ಬದಲಿಸಿ",
        "btn_edit_loc": "📍 ಪ್ರದೇಶ / ನಗರ ಬದಲಿಸಿ",
        "btn_edit_rasi": "✨ ರಾಶಿ ಬದಲಿಸಿ",
        "profile_title": "👤 <b>ನಿಮ್ಮ ಪ್ರೊಫೈಲ್ ಮತ್ತು ಆದ್ಯತೆಗಳು</b>",
        "other_title": "📣 <b>ಇತರೆ ಸೇವೆಗಳು</b>",
        "other_body": "• ದೈನಂದಿನ ಪಂಚಾಂಗ, ರಾಶಿ, ಚಿನ್ನ ದರ / ಬೆಳ್ಳಿ ದರ ಮತ್ತು ಸ್ಥಳೀಯ ಹವಾಮಾನ ಮಾಹಿತಿ.",
        "help_title": "💬 <b>ಬೆಂಬಲ &amp; ಪ್ರತಿಕ್ರಿಯೆ</b>",
        "help_prompt": "ನಿಮ್ಮ ಪ್ರತಿಕ್ರಿಯೆ, ಪ್ರಶ್ನೆ ಅಥವಾ ಸಹಾಯ ವಿನಂತಿಯನ್ನು ಇಲ್ಲಿಯೇ ಚಾಟ್‌ನಲ್ಲಿ ಟೈಪ್ ಮಾಡಿ ಕಳುಹಿಸಿ.",
        "help_received": "🙏 <b>ಧನ್ಯವಾದಗಳು!</b> ನಿಮ್ಮ ಸಂದೇಶವನ್ನು ಸ್ವೀಕರಿಸಲಾಗಿದೆ ಮತ್ತು ನಮ್ಮ ತಂಡಕ್ಕಾಗಿ ದಾಖಲಿಸಲಾಗಿದೆ.",
        "dpdpa_title": "🔒 <b>ಗೌಪ್ಯತೆ ಮತ್ತು ಡೇಟಾ (DPDPA 2023)</b>",
        "dpdpa_body": (
            "• <b>ಉಳಿಸಲಾದ ಮಾಹಿತಿ:</b> ಹೆಸರು, ಭಾಷೆ, ಜನ್ಮ ದಿನಾಂಕ, ಪ್ರದೇಶ/ನಗರ, ರಾಶಿ ಮತ್ತು ನಿಮ್ಮ ಬೆಂಬಲ ಸಂದೇಶಗಳು.\n"
            "• <b>ಉದ್ದೇಶ:</b> ಬೆಳಿಗ್ಗೆ 04:30 AM IST AURA ಕಾರ್ಡ್ ವೈಯಕ್ತೀಕರಣ ಮತ್ತು ಬೆಂಬಲಕ್ಕಾಗಿ.\n"
            "• <b>ನಿಮ್ಮ ಹಕ್ಕುಗಳು:</b> ಪ್ರೊಫೈಲ್‌ನಲ್ಲಿ ಬದಲಿಸಿ ಅಥವಾ <b>ನನ್ನ ಡೇಟಾ ಅಳಿಸಿ (DPDPA)</b> / /delete_data ಮೂಲಕ ಶಾಶ್ವತವಾಗಿ ಅಳಿಸಿ."
        ),
        "confirm_delete_body": "⚠️ <b>ಡೇಟಾ ಅಳಿಸುವಿಕೆ ದೃಢೀಕರಣ (DPDPA 2023):</b>\nನಿಮ್ಮ ಪ್ರೊಫೈಲ್, ಆದ್ಯತೆಗಳು ಮತ್ತು ದಾಖಲೆಗಳನ್ನು ಶಾಶ್ವತವಾಗಿ ಅಳಿಸಲಾಗುತ್ತದೆ.",
        "erased_msg": "🗑️ DPDPA 2023 ಪ್ರಕಾರ ನಿಮ್ಮ ಡೇಟಾ ಶಾಶ್ವತವಾಗಿ ಅಳಿಸಲಾಗಿದೆ. ಮತ್ತೆ ಆರಂಭಿಸಲು /start ಒತ್ತಿರಿ.",
        "saved_msg": "✅ ಉಳಿಸಲಾಗಿದೆ: <b>{val}</b>",
    },
    "ml": {
        "greeting": "നമസ്കാരം, <b>{name}</b> 🙏",
        "schedule": "എല്ലാ ദിവസവും രാവിലെ <b>04:30 AM IST</b>-ന്, നിങ്ങളുടെ ദിവസം ശാന്തമായും ദൈവികമായും ആരംഭിക്കാൻ <b>ആശീർവാദത്തോടെ</b> ഒരു ദിവ്യ സന്ദേശം:",
        "b1": "• 🪔 {blessing_with} 🛕 ക്ഷേത്ര &amp; വിശേഷ അറിയിപ്പുകൾ",
        "b2": "• ✨ {wow}",
        "b3": "• ⏰ ശുഭ സമയം [തീരുമാനങ്ങൾ ആസൂത്രണം ചെയ്യുക]",
        "b4": "• 🟡 {gold_rate} ⚪️ {silver_rate}",
        "b5": "• 🌦 കാലാവസ്ഥ [ദിവസ ആസൂത്രണം]",
        "b6": "• 🌟 {quote}",
        "step1": "<b>ഘട്ടം 1 / 3</b> — നിങ്ങളുടെ ജനനത്തീയതി നൽകുക (ഉദാ: <code>15-08-1985</code>):",
        "invalid_dob": "ദയവായി <code>DD-MM-YYYY</code> മാതൃകയിൽ ശരിയായ ജനനത്തീയതി നൽകുക (ഉദാ: <code>15-08-1985</code>):",
        "step2": (
            "<b>ഘട്ടം 2 / 3</b> — നിങ്ങളുടെ പ്രദേശവും നഗരവും നൽകുക (അല്ലെങ്കിൽ നഗരം മാത്രം):\n"
            "<i>ഉദാഹരണം: <code>Ambattur, Chennai</code> അല്ലെങ്കിൽ <code>Adyar, Chennai</code> (അല്ലെങ്കിൽ <code>Chennai</code>).\n"
            "എന്തുകൊണ്ട്? പ്രദേശം ചേർത്താൽ പ്രാദേശിക കാലാവസ്ഥയും മഴ വിവരവും കൂടുതൽ കൃത്യമാകും.</i>"
        ),
        "invalid_loc": "ദയവായി നിങ്ങളുടെ പ്രദേശവും നഗരവും നൽകുക (ഉദാ: <code>Ambattur, Chennai</code> അല്ലെങ്കിൽ <code>Adyar, Chennai</code>):",
        "step3": "<b>ഘട്ടം 3 / 3</b> — നിങ്ങളുടെ രാശി തിരഞ്ഞെടുക്കുക:",
        "back_lang": "← ഭാഷയിലേക്ക് മടങ്ങുക",
        "back_dob": "← ജനനത്തീയതിയിലേക്ക് മടങ്ങുക",
        "back_loc": "← പ്രദേശം / നഗരത്തിലേക്ക് മടങ്ങുക",
        "back_card": "← കാർഡിലേക്ക് മടങ്ങുക",
        "back_profile": "← പ്രൊഫൈലിലേക്ക് മടങ്ങുക",
        "confirmed_title": "🙏 <b>സബ്സ്ക്രിപ്ഷൻ സ്ഥിരീകരിച്ചു — ആശീർവാദം സജീവം</b>",
        "lbl_name": "പേര്",
        "lbl_lang": "ഭാഷ",
        "lbl_dob": "ജനനത്തീയതി",
        "lbl_loc": "പ്രദേശം / നഗരം",
        "lbl_rasi": "രാശി",
        "lbl_time": "Daily Delivery: <b>04:30 AM IST</b>",
        "btn_sample": "📨 ഇന്നത്തെ കാർഡ് ഇപ്പോൾ അയയ്ക്കുക",
        "btn_profile": "👤 പ്രൊഫൈൽ",
        "btn_other": "📣 മറ്റ് സേവനങ്ങൾ",
        "btn_12pillars": "🏛️ 12 പില്ലേഴ്സ് കാഴ്ച",
        "btn_pay": "🛒 Shop",
        "btn_help": "💬 സഹായവും പ്രതികരണവും",
        "btn_translate": "🌐 Translate [ENG]",
        "btn_close_translation": "✕ Close Translation",
        "btn_privacy": "🔒 സ്വകാര്യത & ഡാറ്റ (DPDPA)",
        "btn_delete": "🗑️ എന്റെ ഡാറ്റ നീക്കം ചെയ്യുക (DPDPA)",
        "btn_confirm_delete": "⚠️ ശാശ്വത നീക്കം സ്ഥിരീകരിക്കുക",
        "btn_edit_name": "✏️ പേര് മാറ്റുക",
        "btn_edit_dob": "🎂 ജനനത്തീയതി മാറ്റുക",
        "btn_edit_lang": "🌐 ഭാഷ മാറ്റുക",
        "btn_edit_loc": "📍 പ്രദേശം / നഗരം മാറ്റുക",
        "btn_edit_rasi": "✨ രാശി മാറ്റുക",
        "profile_title": "👤 <b>നിങ്ങളുടെ പ്രൊഫൈലും മുൻഗണനകളും</b>",
        "other_title": "📣 <b>മറ്റ് സേവനങ്ങൾ</b>",
        "other_body": "• ദൈനംദിന പഞ്ചാംഗം, രാശി, സ്വർണ്ണ നിരക്ക് / വെള്ളി നിരക്ക് &amp; പ്രാദേശിക കാലാവസ്ഥ വിവരങ്ങൾ.",
        "help_title": "💬 <b>സഹായവും പ്രതികരണവും</b>",
        "help_prompt": "നിങ്ങളുടെ അഭിപ്രായം, ചോദ്യം അല്ലെങ്കിൽ സഹായ അഭ്യർത്ഥന ഇവിടെത്തന്നെ ചാറ്റിൽ ടൈപ്പ് ചെയ്ത് അയയ്ക്കുക.",
        "help_received": "🙏 <b>നന്ദി!</b> നിങ്ങളുടെ സന്ദേശം ലഭിക്കുകയും ഞങ്ങളുടെ ടീമിനായി രേഖപ്പെടുത്തുകയും ചെയ്തിട്ടുണ്ട്.",
        "dpdpa_title": "🔒 <b>സ്വകാര്യത &amp; ഡാറ്റ (DPDPA 2023)</b>",
        "dpdpa_body": (
            "• <b>സൂക്ഷിക്കുന്ന വിവരങ്ങൾ:</b> പേര്, ഭാഷ, ജനനത്തീയതി, പ്രദേശം/നഗരം, രാശി, നിങ്ങളുടെ സഹായ സന്ദേശങ്ങൾ.\n"
            "• <b>ഉദ്ദേശ്യം:</b> രാവിലെ 04:30 AM IST AURA കാർഡ് വ്യക്തിഗതമാക്കുന്നതിനും സഹായത്തിനും.\n"
            "• <b>നിങ്ങളുടെ അവകാശങ്ങൾ:</b> പ്രൊഫൈലിൽ മാറ്റാം അല്ലെങ്കിൽ <b>എന്റെ ഡാറ്റ നീക്കം ചെയ്യുക (DPDPA)</b> / /delete_data വഴി പൂർണ്ണമായി നീക്കം ചെയ്യാം."
        ),
        "confirm_delete_body": "⚠️ <b>ഡാറ്റ നീക്കം സ്ഥിരീകരണം (DPDPA 2023):</b>\nനിങ്ങളുടെ പ്രൊഫൈൽ, മുൻഗണനകൾ, രേഖകൾ എന്നിവ ശാശ്വതമായി നീക്കം ചെയ്യപ്പെടും.",
        "erased_msg": "🗑️ DPDPA 2023 പ്രകാരം നിങ്ങളുടെ ഡാറ്റ പൂർണ്ണമായി നീക്കം ചെയ്തു. വീണ്ടും തുടങ്ങാൻ /start അമർത്തുക.",
        "saved_msg": "✅ അപ്ഡേറ്റ് ചെയ്തു: <b>{val}</b>",
    },
}

DB_POOL: Optional[asyncpg.Pool] = None
CACHED_WELCOME_VIDEO_ID: Optional[str] = os.environ.get("WELCOME_VIDEO_FILE_ID", "").strip() or None


def copy_for(lang: Optional[str]) -> dict:
    return WELCOME_COPY.get(lang or "en") or WELCOME_COPY["en"]


def get_wow_label(lang: Optional[str]) -> str:
    return WOW_LABELS.get(lang or "en") or WOW_LABELS["en"]


def get_quote_label(lang: Optional[str]) -> str:
    return QUOTE_LABELS.get(lang or "en") or QUOTE_LABELS["en"]


def get_blessing_with_label(lang: Optional[str]) -> str:
    return BLESSING_WITH_LABELS.get(lang or "en") or BLESSING_WITH_LABELS["en"]


def get_gold_rate_label(lang: Optional[str]) -> str:
    return GOLD_RATE_LABELS.get(lang or "en") or GOLD_RATE_LABELS["en"]


def get_silver_rate_label(lang: Optional[str]) -> str:
    return SILVER_RATE_LABELS.get(lang or "en") or SILVER_RATE_LABELS["en"]


def get_rasi_display(rasi_code: Optional[str], lang: str = "en") -> str:
    code = (rasi_code or "mesham").lower()
    for r_code, _, r_map in RASIS:
        if r_code == code:
            return r_map.get(lang) or r_map["en"]
    return code.title()


# ---------------------------------------------------------------------------
# Database Helpers (asyncpg)
# ---------------------------------------------------------------------------
async def get_db_pool() -> asyncpg.Pool:
    global DB_POOL
    if DB_POOL is None or DB_POOL._closed:
        DB_POOL = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=5)
    return DB_POOL


async def ensure_subscribers_schema() -> None:
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
        CREATE TABLE IF NOT EXISTS support_feedback (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            username TEXT,
            preferred_language VARCHAR(8),
            message_text TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """,
    ]
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            for stmt in ddl_statements:
                await conn.execute(stmt)
        logger.info("Database schema verified successfully.")
    except Exception as exc:
        logger.warning("Schema check notice: %s", exc)


async def upsert_subscriber_profile(
    telegram_id: int,
    first_name: str,
    username: str,
    lang: str,
    dob: str,
    locality: str,
    rasi: str,
) -> None:
    city_part = locality.split(",")[-1].strip() if "," in locality else locality.strip()
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """
                INSERT INTO subscribers (
                    telegram_id, first_name, username, preferred_language,
                    dob, locality, city, rasi, frequency, is_active,
                    consent_given_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 1, TRUE, NOW(), NOW())
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
                telegram_id,
                first_name,
                username,
                lang,
                dob,
                locality,
                city_part,
                rasi,
            )
        except Exception as full_err:
            logger.warning("Full upsert fallback triggered: %s", full_err)
            await conn.execute(
                """
                INSERT INTO subscribers (
                    telegram_id, first_name, preferred_language,
                    dob, city, rasi, is_active
                )
                VALUES ($1, $2, $3, $4, $5, $6, TRUE)
                ON CONFLICT (telegram_id) DO UPDATE SET
                    first_name = EXCLUDED.first_name,
                    preferred_language = EXCLUDED.preferred_language,
                    dob = EXCLUDED.dob,
                    city = EXCLUDED.city,
                    rasi = EXCLUDED.rasi,
                    is_active = TRUE;
                """,
                telegram_id,
                first_name,
                lang,
                dob,
                city_part,
                rasi,
            )


async def update_single_field(telegram_id: int, field: str, value: str) -> None:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if field == "preferred_language":
            await conn.execute(
                "UPDATE subscribers SET preferred_language = $1, updated_at = NOW() WHERE telegram_id = $2;",
                value,
                telegram_id,
            )
        elif field == "first_name":
            await conn.execute(
                "UPDATE subscribers SET first_name = $1, updated_at = NOW() WHERE telegram_id = $2;",
                value,
                telegram_id,
            )
        elif field == "dob":
            await conn.execute(
                "UPDATE subscribers SET dob = $1, updated_at = NOW() WHERE telegram_id = $2;",
                value,
                telegram_id,
            )
        elif field == "locality":
            city_part = value.split(",")[-1].strip() if "," in value else value.strip()
            await conn.execute(
                "UPDATE subscribers SET locality = $1, city = $2, updated_at = NOW() WHERE telegram_id = $3;",
                value,
                city_part,
                telegram_id,
            )
        elif field == "rasi":
            await conn.execute(
                "UPDATE subscribers SET rasi = $1, updated_at = NOW() WHERE telegram_id = $2;",
                value,
                telegram_id,
            )


def parse_payload_dict(raw_payload) -> dict:
    if isinstance(raw_payload, dict):
        return raw_payload
    if isinstance(raw_payload, str):
        try:
            return json.loads(raw_payload)
        except Exception:
            return {}
    return {}


# ---------------------------------------------------------------------------
# Message Tracking, Safe Edit & Cleanup Helpers
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
    ids = context.user_data.get("onboarding_msg_ids", [])
    remaining = []
    for mid in ids:
        if keep_msg_id and mid == keep_msg_id:
            remaining.append(mid)
            continue
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass
    context.user_data["onboarding_msg_ids"] = remaining


async def safe_edit_or_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    query = update.callback_query
    if query and query.message:
        msg = query.message
        has_media = (
            bool(getattr(msg, "photo", None))
            or bool(getattr(msg, "video", None))
            or bool(getattr(msg, "animation", None))
        )
        try:
            if has_media:
                try:
                    await msg.delete()
                except Exception:
                    pass
                sent = await context.bot.send_message(
                    chat_id=msg.chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                )
                track_onboarding_msg(context, sent.message_id)
            else:
                await query.edit_message_text(
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup,
                )
            return
        except BadRequest as exc:
            if "Message is not modified" in str(exc):
                return
            logger.debug("safe_edit_or_reply fallback to send_message: %s", exc)

    if update.effective_chat:
        sent = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )
        track_onboarding_msg(context, sent.message_id)


# ---------------------------------------------------------------------------
# UI Builders
# ---------------------------------------------------------------------------
def build_language_keyboard(lang_prefix: str = "lang") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("English", callback_data=f"{lang_prefix}:en"),
            InlineKeyboardButton("தமிழ் (Tamil)", callback_data=f"{lang_prefix}:ta"),
        ],
        [
            InlineKeyboardButton("हिन्दी (Hindi)", callback_data=f"{lang_prefix}:hi"),
            InlineKeyboardButton("తెలుగు (Telugu)", callback_data=f"{lang_prefix}:te"),
        ],
        [
            InlineKeyboardButton("ಕನ್ನಡ (Kannada)", callback_data=f"{lang_prefix}:kn"),
            InlineKeyboardButton("മലയാളം (Malayalam)", callback_data=f"{lang_prefix}:ml"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def build_language_prompt_text() -> str:
    return (
        f"{CARD_HEADER}"
        "<b>Select</b> your <b>Preferred Language</b> to begin"
    )


def build_welcome_dob_text(first_name: str, lang: str = "en") -> str:
    c = copy_for(lang)
    wow = get_wow_label(lang)
    quote = get_quote_label(lang)
    blessing_with = get_blessing_with_label(lang)
    gold_rate = get_gold_rate_label(lang)
    silver_rate = get_silver_rate_label(lang)
    safe_name = first_name or "Friend"
    return (
        f"{CARD_HEADER}"
        f"{c['greeting'].format(name=safe_name)}\n\n"
        f"{c['schedule']}\n\n"
        f"{c['b1'].format(blessing_with=blessing_with)}\n\n"
        f"{c['b2'].format(wow=wow)}\n\n"
        f"{c['b3']}\n\n"
        f"{c['b4'].format(gold_rate=gold_rate, silver_rate=silver_rate)}\n\n"
        f"{c['b5']}\n\n"
        f"{c['b6'].format(quote=quote)}\n\n"
        f"{c['step1']}"
    )


def build_location_step_text(lang: str, dob: str) -> str:
    c = copy_for(lang)
    lang_label = LANGUAGES.get(lang, "English")
    return (
        f"{CARD_HEADER}"
        f"✓ <b>{c['lbl_lang']}:</b> {lang_label}\n\n"
        f"✓ <b>{c['lbl_dob']}:</b> {dob}\n\n"
        f"{c['step2']}"
    )


def build_rasi_step_text(lang: str, dob: str, locality: str) -> str:
    c = copy_for(lang)
    lang_label = LANGUAGES.get(lang, "English")
    return (
        f"{CARD_HEADER}"
        f"✓ <b>{c['lbl_lang']}:</b> {lang_label}\n\n"
        f"✓ <b>{c['lbl_dob']}:</b> {dob}\n\n"
        f"✓ <b>{c['lbl_loc']}:</b> {locality}\n\n"
        f"{c['step3']}"
    )


def build_rasi_keyboard(lang: str = "en", prefix: str = "rasi", include_back: bool = True) -> InlineKeyboardMarkup:
    c = copy_for(lang)
    rows = []
    for i in range(0, len(RASIS), 3):
        rows.append(
            [
                InlineKeyboardButton(r_map.get(lang) or r_map["en"], callback_data=f"{prefix}:{r_code}")
                for r_code, _, r_map in RASIS[i : i + 3]
            ]
        )
    if include_back:
        rows.append([InlineKeyboardButton(c["back_loc"], callback_data="back:location")])
    return InlineKeyboardMarkup(rows)


def build_daily_action_keyboard(telegram_id: int, lang: str, edition_date: str) -> InlineKeyboardMarkup:
    c = copy_for(lang)
    pay_url = f"{UPI_GATEWAY_CHECKOUT_URL}?uid={telegram_id}&ref={edition_date}"

    rows = [
        [
            InlineKeyboardButton(c["btn_profile"], callback_data="panel:profile"),
            InlineKeyboardButton(c["btn_other"], callback_data="menu:other_services"),
        ],
        [
            InlineKeyboardButton(c["btn_pay"], url=pay_url),
            InlineKeyboardButton(c["btn_help"], callback_data="menu:help_feedback"),
        ],
    ]
    if lang != "en":
        rows.append(
            [InlineKeyboardButton(c["btn_translate"], callback_data=f"translate:en:{edition_date}")]
        )
    return InlineKeyboardMarkup(rows)


async def send_welcome_video_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global CACHED_WELCOME_VIDEO_ID
    chat_id = update.effective_chat.id
    try:
        if CACHED_WELCOME_VIDEO_ID:
            vid = await context.bot.send_video(
                chat_id=chat_id,
                video=CACHED_WELCOME_VIDEO_ID,
                width=WELCOME_VIDEO_WIDTH,
                height=WELCOME_VIDEO_HEIGHT,
                supports_streaming=True,
                read_timeout=90,
                write_timeout=90,
            )
            track_onboarding_msg(context, vid.message_id)
            return
        if WELCOME_VIDEO_PATH.is_file():
            with open(WELCOME_VIDEO_PATH, "rb") as vf:
                vid = await context.bot.send_video(
                    chat_id=chat_id,
                    video=vf,
                    width=WELCOME_VIDEO_WIDTH,
                    height=WELCOME_VIDEO_HEIGHT,
                    supports_streaming=True,
                    read_timeout=120,
                    write_timeout=120,
                )
            track_onboarding_msg(context, vid.message_id)
            if vid.video and vid.video.file_id:
                CACHED_WELCOME_VIDEO_ID = vid.video.file_id
                logger.info("Cached welcome video file_id for fast future sends.")
    except Exception as exc:
        logger.warning("Welcome video skipped: %s", exc)


# ---------------------------------------------------------------------------
# Onboarding Handlers (With Stage Status Feedback During Video/Startup)
# ---------------------------------------------------------------------------
async def start_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    await cleanup_previous_messages(context, chat_id)
    context.user_data.clear()

    if update.message:
        track_onboarding_msg(context, update.message.message_id)

    status_msg = await update.effective_message.reply_text(
        f"{CARD_HEADER}⏳ <b>Step 1/2:</b> Warming up morning grace &amp; welcome video…",
        parse_mode=ParseMode.HTML,
    )
    track_onboarding_msg(context, status_msg.message_id)

    await send_welcome_video_top(update, context)

    try:
        await status_msg.edit_text(
            f"{CARD_HEADER}✨ <b>Step 2/2:</b> Preparing language choices…",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    sent = await update.effective_message.reply_text(
        build_language_prompt_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=build_language_keyboard("lang"),
    )
    track_onboarding_msg(context, sent.message_id)

    try:
        await status_msg.delete()
    except Exception:
        pass

    return LANG


async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    lang_code = query.data.split(":", 1)[1]
    context.user_data["lang"] = lang_code
    c = copy_for(lang_code)

    first_name = update.effective_user.first_name if update.effective_user else "Friend"
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(c["back_lang"], callback_data="back:lang")]]
    )
    await safe_edit_or_reply(update, context, build_welcome_dob_text(first_name, lang_code), reply_markup=kb)
    track_onboarding_msg(context, query.message.message_id)
    return DOB


async def set_dob_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    track_onboarding_msg(context, update.message.message_id)
    lang = context.user_data.get("lang", "en")
    c = copy_for(lang)

    if not re.match(r"^\d{2}[-/]\d{2}[-/]\d{4}$", text):
        warn = await update.message.reply_text(
            f"{CARD_HEADER}{c['invalid_dob']}",
            parse_mode=ParseMode.HTML,
        )
        track_onboarding_msg(context, warn.message_id)
        return DOB

    dob_clean = text.replace("/", "-")
    context.user_data["dob"] = dob_clean

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(c["back_dob"], callback_data="back:dob")]]
    )
    sent = await update.message.reply_text(
        build_location_step_text(lang, dob_clean),
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    track_onboarding_msg(context, sent.message_id)
    return LOCATION


async def set_location_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    locality = (update.message.text or "").strip()
    track_onboarding_msg(context, update.message.message_id)
    lang = context.user_data.get("lang", "en")
    c = copy_for(lang)

    if len(locality) < 2:
        warn = await update.message.reply_text(
            f"{CARD_HEADER}{c['invalid_loc']}",
            parse_mode=ParseMode.HTML,
        )
        track_onboarding_msg(context, warn.message_id)
        return LOCATION

    context.user_data["locality"] = locality
    dob = context.user_data.get("dob", "")

    sent = await update.message.reply_text(
        build_rasi_step_text(lang, dob, locality),
        parse_mode=ParseMode.HTML,
        reply_markup=build_rasi_keyboard(lang),
    )
    track_onboarding_msg(context, sent.message_id)
    return RASI


async def set_rasi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    try:
        rasi_code = query.data.split(":", 1)[1]
        user = update.effective_user
        telegram_id = user.id
        first_name = user.first_name or ""
        username = user.username or ""

        lang = context.user_data.get("lang", "en")
        c = copy_for(lang)
        lang_label = LANGUAGES.get(lang, "English")
        dob = context.user_data.get("dob", "Not set")
        locality = context.user_data.get("locality", "Chennai")
        rasi_display = get_rasi_display(rasi_code, lang)

        await upsert_subscriber_profile(
            telegram_id=telegram_id,
            first_name=first_name,
            username=username,
            lang=lang,
            dob=dob,
            locality=locality,
            rasi=rasi_code,
        )

        await cleanup_previous_messages(
            context,
            chat_id=query.message.chat_id,
            keep_msg_id=query.message.message_id,
        )

        confirmation_text = (
            f"{CARD_HEADER}"
            f"{c['confirmed_title']}\n\n"
            f"✓ <b>{c['lbl_lang']}:</b> {lang_label}\n"
            f"✓ <b>{c['lbl_dob']}:</b> {dob}\n"
            f"✓ <b>{c['lbl_loc']}:</b> {locality}\n"
            f"✓ <b>{c['lbl_rasi']}:</b> {rasi_display}\n"
            f"✓ {c['lbl_time']}"
        )
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(c["btn_sample"], callback_data="send_sample_now")],
                [InlineKeyboardButton(c["btn_profile"], callback_data="panel:profile")],
            ]
        )
        await safe_edit_or_reply(update, context, confirmation_text, reply_markup=kb)
        context.user_data.pop("onboarding_msg_ids", None)
    except Exception as exc:
        logger.exception("Error in set_rasi_callback: %s", exc)
        await safe_edit_or_reply(
            update,
            context,
            f"{CARD_HEADER}⚠️ We hit a temporary snag saving your Rasi. Please tap /start to try again.",
        )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Merged Profile & Preferences, Other Services, In-Telegram Feedback & DPDPA
# ---------------------------------------------------------------------------
async def _get_user_lang_and_row(telegram_id: int, fallback_lang: str = "en"):
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            sub = await conn.fetchrow("SELECT * FROM subscribers WHERE telegram_id = $1;", telegram_id)
    except Exception as exc:
        logger.warning("DB read in panel skipped: %s", exc)
        sub = None
    lang = (sub["preferred_language"] if sub and sub["preferred_language"] else None) or fallback_lang or "en"
    return lang, sub


async def open_profile_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()
    context.user_data.pop("editing_field", None)
    context.user_data.pop("awaiting_feedback", None)

    user = query.from_user if query else update.effective_user
    telegram_id = user.id
    lang, sub = await _get_user_lang_and_row(telegram_id, context.user_data.get("lang", "en"))
    c = copy_for(lang)

    name_val = (sub["first_name"] if sub and sub["first_name"] else None) or user.first_name or "Friend"
    dob_val = (sub["dob"] if sub and sub["dob"] else None) or context.user_data.get("dob") or "Not set"
    lang_label = LANGUAGES.get(lang, "English")
    loc_val = (
        (sub["locality"] if sub and sub["locality"] else None)
        or (sub["city"] if sub and sub["city"] else None)
        or context.user_data.get("locality")
        or "Chennai"
    )
    rasi_code = (sub["rasi"] if sub and sub["rasi"] else None) or "mesham"
    rasi_display = get_rasi_display(rasi_code, lang)
    pillars_status = "ON" if context.user_data.get("12pillars_view", False) else "OFF"

    text = (
        f"{CARD_HEADER}"
        f"{c['profile_title']}\n\n"
        f"• <b>{c['lbl_name']}:</b> {name_val}\n"
        f"• <b>{c['lbl_dob']}:</b> {dob_val}\n"
        f"• <b>{c['lbl_lang']}:</b> {lang_label}\n"
        f"• <b>{c['lbl_loc']}:</b> {loc_val}\n"
        f"• <b>{c['lbl_rasi']}:</b> {rasi_display}\n"
        f"• <b>12 Pillars Mode:</b> {pillars_status}"
    )
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(c["btn_edit_name"], callback_data="editfield:first_name"),
                InlineKeyboardButton(c["btn_edit_dob"], callback_data="editfield:dob"),
            ],
            [
                InlineKeyboardButton(c["btn_edit_lang"], callback_data="editfield:preferred_language"),
                InlineKeyboardButton(c["btn_edit_loc"], callback_data="editfield:locality"),
            ],
            [
                InlineKeyboardButton(c["btn_edit_rasi"], callback_data="editfield:rasi"),
                InlineKeyboardButton(f"{c['btn_12pillars']} ({pillars_status})", callback_data="menu:12pillars_toggle"),
            ],
            [
                InlineKeyboardButton(c["btn_privacy"], callback_data="panel:dpdpa"),
                InlineKeyboardButton(c["btn_delete"], callback_data="action:confirm_delete"),
            ],
            [
                InlineKeyboardButton(c["back_card"], callback_data="back:card"),
            ],
        ]
    )
    await safe_edit_or_reply(update, context, text, reply_markup=kb)


async def open_profile_panel_end_conv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await open_profile_panel(update, context)
    return ConversationHandler.END


async def open_other_services_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.pop("editing_field", None)
    context.user_data.pop("awaiting_feedback", None)

    telegram_id = query.from_user.id
    lang, _ = await _get_user_lang_and_row(telegram_id, context.user_data.get("lang", "en"))
    c = copy_for(lang)

    pillars_mode = bool(context.user_data.get("12pillars_view", False))
    mode_status = "ON" if pillars_mode else "OFF"
    text = f"{CARD_HEADER}{c['other_title']}\n\n{c['other_body']}\n\n• <b>12 Pillars Mode:</b> {mode_status}"
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"{c['btn_12pillars']} ({mode_status})", callback_data="menu:12pillars_toggle")],
            [InlineKeyboardButton(c["back_card"], callback_data="back:card")],
        ]
    )
    await safe_edit_or_reply(update, context, text, reply_markup=kb)


async def toggle_12pillars_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["12pillars_view"] = not bool(context.user_data.get("12pillars_view", False))
    await open_profile_panel(update, context)


async def open_help_feedback_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.pop("editing_field", None)
    context.user_data["awaiting_feedback"] = True

    telegram_id = query.from_user.id
    lang, _ = await _get_user_lang_and_row(telegram_id, context.user_data.get("lang", "en"))
    c = copy_for(lang)

    text = f"{CARD_HEADER}{c['help_title']}\n\n{c['help_prompt']}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(c["back_card"], callback_data="back:card")]])
    await safe_edit_or_reply(update, context, text, reply_markup=kb)
    return FEEDBACK_TEXT


async def save_help_feedback_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    feedback_body = (update.message.text or "").strip()
    user = update.effective_user
    telegram_id = user.id
    username = user.username or user.first_name or ""

    lang, _ = await _get_user_lang_and_row(telegram_id, context.user_data.get("lang", "en"))
    c = copy_for(lang)

    if not feedback_body:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(c["back_card"], callback_data="back:card")]])
        await update.message.reply_text(
            f"{CARD_HEADER}{c['help_prompt']}",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return FEEDBACK_TEXT

    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO support_feedback (telegram_id, username, preferred_language, message_text)
                VALUES ($1, $2, $3, $4);
                """,
                telegram_id,
                username,
                lang,
                feedback_body,
            )
    except Exception as exc:
        logger.warning("Support feedback DB insert notice: %s", exc)

    if ADMIN_SUPPORT_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=int(ADMIN_SUPPORT_CHAT_ID),
                text=(
                    f"📩 <b>AURA Help &amp; Feedback</b>\n"
                    f"• <b>User ID:</b> <code>{telegram_id}</code> ({username})\n"
                    f"• <b>Lang:</b> {lang}\n\n"
                    f"{feedback_body}"
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            logger.warning("Admin support forward notice: %s", exc)

    context.user_data.pop("awaiting_feedback", None)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(c["back_card"], callback_data="back:card")]])
    await update.message.reply_text(
        f"{CARD_HEADER}{c['help_received']}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    return ConversationHandler.END


async def open_dpdpa_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    telegram_id = query.from_user.id
    lang, _ = await _get_user_lang_and_row(telegram_id, context.user_data.get("lang", "en"))
    c = copy_for(lang)

    text = f"{CARD_HEADER}{c['dpdpa_title']}\n\n{c['dpdpa_body']}"
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(c["btn_delete"], callback_data="action:confirm_delete")],
            [InlineKeyboardButton(c["back_profile"], callback_data="back:profile")],
        ]
    )
    await safe_edit_or_reply(update, context, text, reply_markup=kb)


async def confirm_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    telegram_id = query.from_user.id
    lang, _ = await _get_user_lang_and_row(telegram_id, context.user_data.get("lang", "en"))
    c = copy_for(lang)

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(c["btn_confirm_delete"], callback_data="action:delete_data")],
            [InlineKeyboardButton(c["back_profile"], callback_data="back:profile")],
        ]
    )
    await safe_edit_or_reply(update, context, f"{CARD_HEADER}{c['confirm_delete_body']}", reply_markup=kb)


async def start_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    field = query.data.split(":", 1)[1]
    context.user_data.pop("awaiting_feedback", None)
    context.user_data["editing_field"] = field

    telegram_id = query.from_user.id
    lang, _ = await _get_user_lang_and_row(telegram_id, context.user_data.get("lang", "en"))
    c = copy_for(lang)

    if field == "preferred_language":
        rows = build_language_keyboard("editval_lang").inline_keyboard
        kb = InlineKeyboardMarkup(list(rows) + [[InlineKeyboardButton(c["back_profile"], callback_data="back:profile")]])
        await safe_edit_or_reply(update, context, build_language_prompt_text(), reply_markup=kb)
        return EDIT_VALUE

    if field == "rasi":
        rows = build_rasi_keyboard(lang=lang, prefix="editval_rasi", include_back=False).inline_keyboard
        kb = InlineKeyboardMarkup(list(rows) + [[InlineKeyboardButton(c["back_profile"], callback_data="back:profile")]])
        await safe_edit_or_reply(update, context, f"{CARD_HEADER}{c['step3']}", reply_markup=kb)
        return EDIT_VALUE

    prompts = {
        "first_name": f"{CARD_HEADER}<b>{c['btn_edit_name']}</b>:",
        "dob": f"{CARD_HEADER}{c['step1']}",
        "locality": f"{CARD_HEADER}{c['step2']}",
    }
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(c["back_profile"], callback_data="back:profile")]])
    await safe_edit_or_reply(
        update,
        context,
        prompts.get(field, f"{CARD_HEADER}Enter new value:"),
        reply_markup=kb,
    )
    return EDIT_VALUE


async def finish_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    prefix, val = query.data.split(":", 1)
    telegram_id = query.from_user.id

    if prefix == "editval_lang":
        await update_single_field(telegram_id, "preferred_language", val)
        context.user_data["lang"] = val
        saved_label = LANGUAGES.get(val, val)
        lang_out = val
    else:
        await update_single_field(telegram_id, "rasi", val)
        lang_out, _ = await _get_user_lang_and_row(telegram_id, context.user_data.get("lang", "en"))
        saved_label = get_rasi_display(val, lang_out)

    context.user_data.pop("editing_field", None)
    c = copy_for(lang_out)
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(c["btn_profile"], callback_data="panel:profile")],
            [InlineKeyboardButton(c["back_card"], callback_data="back:card")],
        ]
    )
    await safe_edit_or_reply(
        update,
        context,
        f"{CARD_HEADER}{c['saved_msg'].format(val=saved_label)}",
        reply_markup=kb,
    )
    return ConversationHandler.END


async def handle_free_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data.get("awaiting_feedback"):
        return await save_help_feedback_message(update, context)

    field = context.user_data.get("editing_field")
    if not field:
        return ConversationHandler.END

    raw = (update.message.text or "").strip()
    telegram_id = update.effective_user.id

    lang, _ = await _get_user_lang_and_row(telegram_id, context.user_data.get("lang", "en"))
    c = copy_for(lang)
    retry_kb = InlineKeyboardMarkup([[InlineKeyboardButton(c["back_profile"], callback_data="back:profile")]])

    if field == "dob":
        if not re.match(r"^\d{2}[-/]\d{2}[-/]\d{4}$", raw):
            await update.message.reply_text(
                f"{CARD_HEADER}{c['invalid_dob']}",
                parse_mode=ParseMode.HTML,
                reply_markup=retry_kb,
            )
            return EDIT_VALUE
        clean_val = raw.replace("/", "-")
        context.user_data["dob"] = clean_val
    elif field == "locality":
        if len(raw) < 2:
            await update.message.reply_text(
                f"{CARD_HEADER}{c['invalid_loc']}",
                parse_mode=ParseMode.HTML,
                reply_markup=retry_kb,
            )
            return EDIT_VALUE
        clean_val = raw
        context.user_data["locality"] = clean_val
    else:
        clean_val = raw[:80] or (update.effective_user.first_name or "Friend")

    await update_single_field(telegram_id, field, clean_val)
    context.user_data.pop("editing_field", None)

    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(c["btn_profile"], callback_data="panel:profile")],
            [InlineKeyboardButton(c["back_card"], callback_data="back:card")],
        ]
    )
    await update.message.reply_text(
        f"{CARD_HEADER}{c['saved_msg'].format(val=clean_val)}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Back Navigation Handlers (With Previous Message Cleanup)
# ---------------------------------------------------------------------------
async def back_navigation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    target = query.data.split(":", 1)[1]
    context.user_data.pop("editing_field", None)
    context.user_data.pop("awaiting_feedback", None)

    if target in ("profile", "settings"):
        await open_profile_panel(update, context)
        return ConversationHandler.END

    if target == "card":
        await send_sample_card_callback(update, context)
        return ConversationHandler.END

    chat_id = query.message.chat_id
    current_msg_id = query.message.message_id
    lang = context.user_data.get("lang", "en")
    c = copy_for(lang)

    await cleanup_previous_messages(context, chat_id=chat_id, keep_msg_id=current_msg_id)
    track_onboarding_msg(context, current_msg_id)

    if target == "lang":
        await safe_edit_or_reply(
            update,
            context,
            build_language_prompt_text(),
            reply_markup=build_language_keyboard("lang"),
        )
        return LANG

    if target == "dob":
        first_name = update.effective_user.first_name if update.effective_user else "Friend"
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(c["back_lang"], callback_data="back:lang")]]
        )
        await safe_edit_or_reply(
            update,
            context,
            build_welcome_dob_text(first_name, lang),
            reply_markup=kb,
        )
        return DOB

    if target == "location":
        dob = context.user_data.get("dob", "")
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(c["back_dob"], callback_data="back:dob")]]
        )
        await safe_edit_or_reply(
            update,
            context,
            build_location_step_text(lang, dob),
            reply_markup=kb,
        )
        return LOCATION

    return LANG


# ---------------------------------------------------------------------------
# Instant Sample Card, Translate & Data Erasure Handlers
# ---------------------------------------------------------------------------
def _build_card_message_from_cache(
    cache: dict,
    lang: str,
    rasi: str,
    city: str,
    today_ist: date,
) -> str:
    wow = get_wow_label(lang)
    quote = get_quote_label(lang)
    defaults = LOCALIZED_CARD_DEFAULTS.get(lang) or LOCALIZED_CARD_DEFAULTS["en"]

    deity_dict = cache.get(("DEITY_DAY", "TODAY")) or {}
    deity_block = deity_dict.get(lang) or defaults["deity"]

    rasi_dict = cache.get(("RASI", rasi)) or {}
    raw_wow = rasi_dict.get(lang) or defaults["wow"]
    wow_block = raw_wow.replace("🌟 <b>Rasi Guidance:</b>", f"✨ <b>{wow}:</b>")

    ausp_dict = cache.get(("AUSPICIOUS", city)) or cache.get(("AUSPICIOUS", "chennai")) or {}
    raw_ausp = ausp_dict.get(lang) or defaults["ausp"]
    ausp_block = raw_ausp.replace("⏳ <b>Auspicious Timing", "⏰ <b>Auspicious Timing")

    gold_dict = cache.get(("GOLD_INR", "INDIA")) or {}
    gold_block = gold_dict.get(lang) or defaults["gold"].format(date=today_ist.strftime("%d %b %Y"))

    weather_dict = cache.get(("WEATHER", city)) or cache.get(("WEATHER", "chennai")) or {}
    weather_block = weather_dict.get(lang) or defaults["weather"]

    quote_dict = cache.get(("QUOTE", "TODAY")) or {}
    raw_quote = quote_dict.get(lang) or defaults["quote"]
    quote_block = raw_quote.replace(f"✨ <b>{wow}:</b>", f"🌟 <b>{quote}:</b>").replace(
        "✨ <b>WoW [Words of Wisdom]:</b>", f"🌟 <b>{quote}:</b>"
    )

    return (
        f"{CARD_HEADER}"
        f"{deity_block}\n\n"
        f"{wow_block}\n\n"
        f"{ausp_block}\n\n"
        f"{gold_block}\n\n"
        f"{weather_block}\n\n"
        f"{quote_block}"
    )


async def send_sample_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()
    context.user_data.pop("editing_field", None)
    context.user_data.pop("awaiting_feedback", None)

    telegram_id = update.effective_user.id
    today_ist = datetime.now(IST).date()

    sub = None
    rows = []
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            sub = await conn.fetchrow("SELECT * FROM subscribers WHERE telegram_id = $1;", telegram_id)
            rows = await conn.fetch(
                "SELECT bucket_type, bucket_key, payload FROM daily_shared_cache WHERE edition_date = $1;",
                today_ist,
            )
            if not rows:
                rows = await conn.fetch(
                    "SELECT bucket_type, bucket_key, payload FROM daily_shared_cache ORDER BY edition_date DESC LIMIT 30;"
                )
    except Exception as exc:
        logger.warning("Cache/DB lookup fallback in send_sample_card_callback: %s", exc)

    lang = (sub["preferred_language"] if sub and sub["preferred_language"] else None) or context.user_data.get("lang") or "en"
    rasi = ((sub["rasi"] if sub and sub["rasi"] else None) or "mesham").lower()
    city = ((sub["city"] if sub and sub["city"] else None) or "chennai").lower()

    cache = {(r["bucket_type"], r["bucket_key"]): parse_payload_dict(r["payload"]) for r in rows}
    message_text = _build_card_message_from_cache(cache, lang, rasi, city, today_ist)

    await safe_edit_or_reply(
        update,
        context,
        message_text,
        reply_markup=build_daily_action_keyboard(telegram_id, lang, str(today_ist)),
    )


async def translate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, _, edition_date_str = query.data.split(":")
    edition_date = date.fromisoformat(edition_date_str)
    telegram_id = update.effective_user.id

    sub = None
    rows = []
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            sub = await conn.fetchrow("SELECT * FROM subscribers WHERE telegram_id = $1;", telegram_id)
            rows = await conn.fetch(
                "SELECT bucket_type, bucket_key, payload FROM daily_shared_cache WHERE edition_date = $1;",
                edition_date,
            )
    except Exception as exc:
        logger.warning("Translate lookup fallback: %s", exc)

    rasi = ((sub["rasi"] if sub and sub["rasi"] else None) or "mesham").lower()
    city = ((sub["city"] if sub and sub["city"] else None) or "chennai").lower()
    cache = {(r["bucket_type"], r["bucket_key"]): parse_payload_dict(r["payload"]) for r in rows}

    en_text = _build_card_message_from_cache(cache, "en", rasi, city, edition_date)
    close_kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("✕ Close Translation", callback_data="close_translation")]]
    )
    await query.message.reply_text(en_text, parse_mode=ParseMode.HTML, reply_markup=close_kb)


async def close_translation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.message:
        try:
            await query.message.delete()
        except Exception:
            pass


async def delete_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    telegram_id = update.effective_user.id
    lang, _ = await _get_user_lang_and_row(telegram_id, context.user_data.get("lang", "en"))
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM subscribers WHERE telegram_id = $1;", telegram_id)
            await conn.execute("DELETE FROM support_feedback WHERE telegram_id = $1;", telegram_id)
            try:
                await conn.execute("DELETE FROM message_ratings WHERE telegram_id = $1;", telegram_id)
            except Exception:
                pass
    except Exception as exc:
        logger.warning("Delete data command DB error: %s", exc)

    context.user_data.clear()
    c = copy_for(lang)
    await update.message.reply_text(f"{CARD_HEADER}{c['erased_msg']}", parse_mode=ParseMode.HTML)


async def delete_data_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    telegram_id = query.from_user.id
    lang, _ = await _get_user_lang_and_row(telegram_id, context.user_data.get("lang", "en"))
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM subscribers WHERE telegram_id = $1;", telegram_id)
            await conn.execute("DELETE FROM support_feedback WHERE telegram_id = $1;", telegram_id)
            try:
                await conn.execute("DELETE FROM message_ratings WHERE telegram_id = $1;", telegram_id)
            except Exception:
                pass
    except Exception as exc:
        logger.warning("Delete data callback DB error: %s", exc)

    context.user_data.clear()
    c = copy_for(lang)
    await safe_edit_or_reply(update, context, f"{CARD_HEADER}{c['erased_msg']}")


# ---------------------------------------------------------------------------
# Health Check & Polling Runner (Render)
# ---------------------------------------------------------------------------
async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "aura-telegram-bot"})


async def post_init(application: Application) -> None:
    await ensure_subscribers_schema()


def build_application() -> Application:
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .read_timeout(90)
        .write_timeout(90)
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
            EDIT_VALUE: [
                CallbackQueryHandler(finish_edit_callback, pattern=r"^editval_(lang|rasi):"),
                CallbackQueryHandler(back_navigation_callback, pattern=r"^back:"),
                CallbackQueryHandler(open_profile_panel_end_conv, pattern=r"^panel:(profile|settings)$"),
                CallbackQueryHandler(open_other_services_panel, pattern=r"^menu:other_services$"),
                CallbackQueryHandler(toggle_12pillars_callback, pattern=r"^menu:12pillars_toggle$"),
                CallbackQueryHandler(open_help_feedback_panel, pattern=r"^menu:help_feedback$"),
                CallbackQueryHandler(confirm_delete_callback, pattern=r"^action:confirm_delete$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text_input),
            ],
            FEEDBACK_TEXT: [
                CallbackQueryHandler(back_navigation_callback, pattern=r"^back:"),
                CallbackQueryHandler(open_profile_panel_end_conv, pattern=r"^panel:(profile|settings)$"),
                CallbackQueryHandler(open_other_services_panel, pattern=r"^menu:other_services$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_help_feedback_message),
            ],
        },
        fallbacks=[
            CommandHandler("start", start_onboarding),
            CallbackQueryHandler(back_navigation_callback, pattern=r"^back:"),
            CallbackQueryHandler(set_rasi_callback, pattern=r"^rasi:"),
            CallbackQueryHandler(open_profile_panel_end_conv, pattern=r"^panel:(profile|settings)$"),
            CallbackQueryHandler(open_other_services_panel, pattern=r"^menu:other_services$"),
            CallbackQueryHandler(toggle_12pillars_callback, pattern=r"^menu:12pillars_toggle$"),
            CallbackQueryHandler(open_help_feedback_panel, pattern=r"^menu:help_feedback$"),
            CallbackQueryHandler(confirm_delete_callback, pattern=r"^action:confirm_delete$"),
        ],
        per_message=False,
    )

    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(open_profile_panel, pattern=r"^panel:(profile|settings)$"))
    app.add_handler(CallbackQueryHandler(open_other_services_panel, pattern=r"^menu:other_services$"))
    app.add_handler(CallbackQueryHandler(toggle_12pillars_callback, pattern=r"^menu:12pillars_toggle$"))
    app.add_handler(CallbackQueryHandler(open_help_feedback_panel, pattern=r"^menu:help_feedback$"))
    app.add_handler(CallbackQueryHandler(open_dpdpa_panel, pattern=r"^panel:dpdpa$"))
    app.add_handler(CallbackQueryHandler(confirm_delete_callback, pattern=r"^action:confirm_delete$"))
    app.add_handler(CallbackQueryHandler(start_edit_field, pattern=r"^editfield:"))
    app.add_handler(CallbackQueryHandler(finish_edit_callback, pattern=r"^editval_(lang|rasi):"))
    app.add_handler(CallbackQueryHandler(delete_data_callback, pattern=r"^action:delete_data$"))
    app.add_handler(CallbackQueryHandler(send_sample_card_callback, pattern=r"^send_sample_now$"))
    app.add_handler(CallbackQueryHandler(translate_callback, pattern=r"^translate:"))
    app.add_handler(CallbackQueryHandler(close_translation_callback, pattern=r"^close_translation$"))
    app.add_handler(CommandHandler("delete_data", delete_data_command))
    app.add_handler(CommandHandler("stop", delete_data_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text_input))
    app.add_handler(CallbackQueryHandler(set_language_callback, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(set_rasi_callback, pattern=r"^rasi:"))
    app.add_handler(CallbackQueryHandler(back_navigation_callback, pattern=r"^back:"))
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

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
