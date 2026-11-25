import os
import re
import json
import asyncio
import logging
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
SUPPORT_FORM_URLS = json.loads(os.environ.get("SUPPORT_FORM_URLS_JSON", "{}"))

IST = timezone(timedelta(hours=5, minutes=30))

# Conversation states
LANG, DOB, LOCATION, RASI = range(4)

CARD_HEADER = (
    "ॐ  <b>AURA</b>  |  Daily Morning Grace &amp; Divine Blessings  ॐ\n"
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

WELCOME_COPY = {
    "en": {
        "greeting": "Namaskaram, <b>{name}</b> 🙏",
        "schedule": "Every morning at <b>04:30 AM IST</b>, receive one calm and divine message to start your day with <b>Ashirvad:</b>",
        "b1": "• 🪔 Daily Blessing + 🛕 Temple &amp; Occasion Alerts",
        "b2": "• ⏳ Auspicious Timing",
        "b3": "• ✨ WoW [Words of Wisdom]",
        "b4": "• 🟡 Gold &amp; ⚪ Silver Rates",
        "b5": "• 🌦 Weather [Plan Your Day]",
        "step1": "<b>Step 1 of 3</b> — Enter your Date of Birth (e.g., <code>15-08-1985</code>):",
        "invalid_dob": "Please enter a valid Date of Birth in <code>DD-MM-YYYY</code> format (e.g., <code>15-08-1985</code>):",
        "step2": (
            "<b>Step 2 of 3</b> — Enter your Locality &amp; City (or just your City):\n"
            "<i>Example: Ambattur, Chennai, Adyar, Chennai, or Chennai\n"
            "Why? Adding your locality gives sharper local weather &amp; rain updates.</i>"
        ),
        "invalid_loc": "Please enter your Locality &amp; City (e.g., <code>Adyar, Chennai</code>):",
        "step3": "<b>Step 3 of 3</b> — Select your Zodiac / Rasi:",
        "back_lang": "← Back to Language",
        "back_dob": "← Back to Date of Birth",
        "back_loc": "← Back to Locality / City",
        "confirmed_title": "🙏 <b>Subscription Confirmed — Ashirvad Active</b>",
        "lbl_lang": "Language",
        "lbl_dob": "Date of Birth",
        "lbl_loc": "Locality / City",
        "lbl_rasi": "Zodiac / Rasi",
        "lbl_time": "Daily Delivery: <b>04:30 AM IST</b>",
        "footer_note": "Update preferences anytime with /start or erase your data with /delete_data.",
        "btn_sample": "📨 Send Today's Card Now",
        "btn_edit": "⚙️ Edit Preferences",
        "btn_other": "✨ Other Services",
        "btn_pay": "🙏 Support / Dakshina",
        "btn_help": "💬 Help & Feedback",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "ta": {
        "greeting": "நமஸ்காரம், <b>{name}</b> 🙏",
        "schedule": "தினமும் காலை <b>04:30 AM IST</b> மணிக்கு, உங்கள் நாளை அமைதியுடனும் தெய்வீக அருளுடனும் தொடங்க <b>ஆசீர்வாதத்துடன்</b> ஒரு தெய்வீகச் செய்தி:",
        "b1": "• 🪔 தினசரி ஆசீர்வாதம் + 🛕 கோவில் &amp; விசேஷ அறிவிப்புகள்",
        "b2": "• ⏳ நல்ல நேரம்",
        "b3": "• ✨ WoW [Words of Wisdom]",
        "b4": "• 🟡 தங்கம் &amp; ⚪ வெள்ளி விலைகள்",
        "b5": "• 🌦 வானிலை [நாளைய திட்டம்]",
        "step1": "<b>படி 1 / 3</b> — உங்கள் பிறந்த தேதியை உள்ளிடவும் (உதா: <code>15-08-1985</code>):",
        "invalid_dob": "சரியான பிறந்த தேதியை <code>DD-MM-YYYY</code> வடிவில் உள்ளிடவும் (உதா: <code>15-08-1985</code>):",
        "step2": (
            "<b>படி 2 / 3</b> — உங்கள் பகுதி மற்றும் நகரத்தை உள்ளிடவும் (அல்லது நகரம் மட்டும்):\n"
            "<i>உதாரணம்: Ambattur, Chennai, Adyar, Chennai, அல்லது Chennai\n"
            "ஏன்? பகுதியைச் சேர்த்தால் அருகிலுள்ள மழை மற்றும் வானிலை தகவல் துல்லியமாக இருக்கும்.</i>"
        ),
        "invalid_loc": "உங்கள் பகுதி மற்றும் நகரத்தை உள்ளிடவும் (உதா: <code>Adyar, Chennai</code>):",
        "step3": "<b>படி 3 / 3</b> — உங்கள் ராசியைத் தேர்ந்தெடுக்கவும்:",
        "back_lang": "← மொழிக்குத் திரும்புக",
        "back_dob": "← பிறந்த தேதிக்குத் திரும்புக",
        "back_loc": "← பகுதி / நகரத்திற்குத் திரும்புக",
        "confirmed_title": "🙏 <b>பதிவு உறுதி செய்யப்பட்டது — ஆசீர்வாதம் செயலில் உள்ளது</b>",
        "lbl_lang": "மொழி",
        "lbl_dob": "பிறந்த தேதி",
        "lbl_loc": "பகுதி / நகரம்",
        "lbl_rasi": "ராசி",
        "lbl_time": "தினசரி நேரம்: <b>04:30 AM IST</b>",
        "footer_note": "/start மூலம் விவரங்களை மாற்றலாம் அல்லது /delete_data மூலம் தரவை நீக்கலாம்.",
        "btn_sample": "📨 இன்றைய அட்டையை அனுப்புக",
        "btn_edit": "⚙️ விருப்பங்களை மாற்றுக",
        "btn_other": "✨ மற்ற சேவைகள்",
        "btn_pay": "🙏 ஆதரவு / தட்சிணை",
        "btn_help": "💬 உதவி & கருத்து",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "hi": {
        "greeting": "नमस्कार, <b>{name}</b> 🙏",
        "schedule": "हर सुबह <b>04:30 AM IST</b> पर, अपने दिन की शांत और दिव्य शुरुआत के लिए <b>आशीर्वाद</b> के साथ एक पावन संदेश प्राप्त करें:",
        "b1": "• 🪔 दैनिक आशीर्वाद + 🛕 मंदिर व विशेष पर्व अलर्ट",
        "b2": "• ⏳ शुभ समय",
        "b3": "• ✨ WoW [Words of Wisdom]",
        "b4": "• 🟡 सोना व ⚪ चांदी के भाव",
        "b5": "• 🌦 मौसम [दिन की योजना]",
        "step1": "<b>चरण 1 / 3</b> — अपनी जन्म तिथि दर्ज करें (उदा: <code>15-08-1985</code>):",
        "invalid_dob": "कृपया <code>DD-MM-YYYY</code> प्रारूप में मान्य जन्म तिथि दर्ज करें (उदा: <code>15-08-1985</code>):",
        "step2": (
            "<b>चरण 2 / 3</b> — अपना क्षेत्र और शहर दर्ज करें (या केवल शहर):\n"
            "<i>उदाहरण: Ambattur, Chennai, Adyar, Chennai, या Chennai\n"
            "क्यों? क्षेत्र जोड़ने से आपके इलाके के अनुसार मौसम की जानकारी अधिक सटीक मिलती है।</i>"
        ),
        "invalid_loc": "कृपया अपना क्षेत्र और शहर दर्ज करें (उदा: <code>Adyar, Chennai</code>):",
        "step3": "<b>चरण 3 / 3</b> — अपनी राशि चुनें:",
        "back_lang": "← भाषा पर वापस जाएं",
        "back_dob": "← जन्म तिथि पर वापस जाएं",
        "back_loc": "← क्षेत्र / शहर पर वापस जाएं",
        "confirmed_title": "🙏 <b>सदस्यता पुष्टि — आशीर्वाद सक्रिय</b>",
        "lbl_lang": "भाषा",
        "lbl_dob": "जन्म तिथि",
        "lbl_loc": "क्षेत्र / शहर",
        "lbl_rasi": "राशि",
        "lbl_time": "दैनिक समय: <b>04:30 AM IST</b>",
        "footer_note": "/start से विवरण बदलें या /delete_data से अपना डेटा हटाएं।",
        "btn_sample": "📨 आज का कार्ड अभी भेजें",
        "btn_edit": "⚙️ प्राथमिकताएं बदलें",
        "btn_other": "✨ अन्य सेवाएं",
        "btn_pay": "🙏 सहयोग / दक्षिणा",
        "btn_help": "💬 सहायता व प्रतिक्रिया",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "te": {
        "greeting": "నమస్కారం, <b>{name}</b> 🙏",
        "schedule": "ప్రతిరోజూ ఉదయం <b>04:30 AM IST</b> గంటలకు, మీ రోజును ప్రశాంతంగా మరియు దైవికంగా ప్రారంభించడానికి <b>ఆశీర్వాదంతో</b> ఒక దివ్య సందేశం:",
        "b1": "• 🪔 రోజువారీ ఆశీర్వాదం + 🛕 ఆలయ &amp; ప్రత్యేక విశేషాలు",
        "b2": "• ⏳ శుభ సమయం",
        "b3": "• ✨ WoW [Words of Wisdom]",
        "b4": "• 🟡 బంగారం &amp; ⚪ వెండి ధరలు",
        "b5": "• 🌦 వాతావరణం [రోజు ప్రణాళిక]",
        "step1": "<b>దశ 1 / 3</b> — మీ పుట్టిన తేదీని నమోదు చేయండి (ఉదా: <code>15-08-1985</code>):",
        "invalid_dob": "దయచేసి <code>DD-MM-YYYY</code> రూపంలో సరైన పుట్టిన తేదీని నమోదు చేయండి (ఉదా: <code>15-08-1985</code>):",
        "step2": (
            "<b>దశ 2 / 3</b> — మీ ప్రాంతం మరియు నగరాన్ని నమోదు చేయండి (లేదా నగరం మాత్రమే):\n"
            "<i>ఉదాహరణ: Ambattur, Chennai, Adyar, Chennai, లేదా Chennai\n"
            "ఎందుకు? ప్రాంతం చేరిస్తే స్థానిక వాతావరణ &amp; వర్ష సమాచారం మరింత ఖచ్చితంగా ఉంటుంది.</i>"
        ),
        "invalid_loc": "దయచేసి మీ ప్రాంతం మరియు నగరాన్ని నమోదు చేయండి (ఉదా: <code>Adyar, Chennai</code>):",
        "step3": "<b>దశ 3 / 3</b> — మీ రాశిని ఎంచుకోండి:",
        "back_lang": "← భాషకు తిరిగి వెళ్ళండి",
        "back_dob": "← పుట్టిన తేదీకి తిరిగి వెళ్ళండి",
        "back_loc": "← ప్రాంతం / నగరానికి తిరిగి వెళ్ళండి",
        "confirmed_title": "🙏 <b>సబ్‌స్క్రిప్షన్ నిర్ధారించబడింది — ఆశీర్వాదం యాక్టివ్</b>",
        "lbl_lang": "భాష",
        "lbl_dob": "పుట్టిన తేదీ",
        "lbl_loc": "ప్రాంతం / నగరం",
        "lbl_rasi": "రాశి",
        "lbl_time": "రోజువారీ సమయం: <b>04:30 AM IST</b>",
        "footer_note": "/start తో వివరాలు మార్చండి లేదా /delete_data తో డేటా తొలగించండి.",
        "btn_sample": "📨 నేటి కార్డ్ ఇప్పుడే పంపండి",
        "btn_edit": "⚙️ ప్రాధాన్యతలు మార్చండి",
        "btn_other": "✨ ఇతర సేవలు",
        "btn_pay": "🙏 సహకారం / దక్షిణ",
        "btn_help": "💬 సహాయం &amp; అభిప్రాయం",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "kn": {
        "greeting": "ನಮಸ್ಕಾರ, <b>{name}</b> 🙏",
        "schedule": "ಪ್ರತಿದಿನ ಬೆಳಿಗ್ಗೆ <b>04:30 AM IST</b> ಗಂಟೆಗೆ, ನಿಮ್ಮ ದಿನವನ್ನು ಶಾಂತವಾಗಿ ಮತ್ತು ದೈವಿಕವಾಗಿ ಆರಂಭಿಸಲು <b>ಆಶೀರ್ವಾದದೊಂದಿಗೆ</b> ಒಂದು ದಿವ್ಯ ಸಂದೇಶ:",
        "b1": "• 🪔 ದೈನಂದಿನ ಆಶೀರ್ವಾದ + 🛕 ದೇವಾಲಯ &amp; ವಿಶೇಷ ಮಾಹಿತಿ",
        "b2": "• ⏳ ಶುಭ ಸಮಯ",
        "b3": "• ✨ WoW [Words of Wisdom]",
        "b4": "• 🟡 ಚಿನ್ನ &amp; ⚪ ಬೆಳ್ಳಿ ದರಗಳು",
        "b5": "• 🌦 ಹವಾಮಾನ [ದಿನದ ಯೋಜನೆ]",
        "step1": "<b>ಹಂತ 1 / 3</b> — ನಿಮ್ಮ ಜನ್ಮ ದಿನಾಂಕವನ್ನು ನಮೂದಿಸಿ (ಉದಾ: <code>15-08-1985</code>):",
        "invalid_dob": "ದಯವಿಟ್ಟು <code>DD-MM-YYYY</code> ನಮೂನೆಯಲ್ಲಿ ಸರಿಯಾದ ಜನ್ಮ ದಿನಾಂಕವನ್ನು ನಮೂದಿಸಿ (ಉದಾ: <code>15-08-1985</code>):",
        "step2": (
            "<b>ಹಂತ 2 / 3</b> — ನಿಮ್ಮ ಪ್ರದೇಶ ಮತ್ತು ನಗರವನ್ನು ನಮೂದಿಸಿ (ಅಥವಾ ನಗರ ಮಾತ್ರ):\n"
            "<i>ಉದಾಹರಣೆ: Ambattur, Chennai, Adyar, Chennai, ಅಥವಾ Chennai\n"
            "ಏಕೆ? ಪ್ರದೇಶ ಸೇರಿಸಿದರೆ ಸ್ಥಳೀಯ ಹವಾಮಾನ ಮತ್ತು ಮಳೆ ಮಾಹಿತಿ ಹೆಚ್ಚು ನಿಖರವಾಗಿರುತ್ತದೆ.</i>"
        ),
        "invalid_loc": "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಪ್ರದೇಶ ಮತ್ತು ನಗರವನ್ನು ನಮೂದಿಸಿ (ಉದಾ: <code>Adyar, Chennai</code>):",
        "step3": "<b>ಹಂತ 3 / 3</b> — ನಿಮ್ಮ ರಾಶಿಯನ್ನು ಆಯ್ಕೆಮಾಡಿ:",
        "back_lang": "← ಭಾಷೆಗೆ ಹಿಂತಿರುಗಿ",
        "back_dob": "← ಜನ್ಮ ದಿನಾಂಕಕ್ಕೆ ಹಿಂತಿರುಗಿ",
        "back_loc": "← ಪ್ರದೇಶ / ನಗರಕ್ಕೆ ಹಿಂತಿರುಗಿ",
        "confirmed_title": "🙏 <b>ಚಂದಾದಾರಿಕೆ ದೃಢೀಕೃತ — ಆಶೀರ್ವಾದ ಸಕ್ರಿಯ</b>",
        "lbl_lang": "ಭಾಷೆ",
        "lbl_dob": "ಜನ್ಮ ದಿನಾಂಕ",
        "lbl_loc": "ಪ್ರದೇಶ / ನಗರ",
        "lbl_rasi": "ರಾಶಿ",
        "lbl_time": "ದೈನಂದಿನ ಸಮಯ: <b>04:30 AM IST</b>",
        "footer_note": "/start ಮೂಲಕ ವಿವರ ಬದಲಿಸಿ ಅಥವಾ /delete_data ಮೂಲಕ ಡೇಟಾ ಅಳಿಸಿ.",
        "btn_sample": "📨 ಇಂದಿನ ಕಾರ್ಡ್ ಈಗ ಕಳುಹಿಸಿ",
        "btn_edit": "⚙️ ಆದ್ಯತೆಗಳನ್ನು ಬದಲಿಸಿ",
        "btn_other": "✨ ಇತರೆ ಸೇವೆಗಳು",
        "btn_pay": "🙏 ಸಹಾಯ / ದಕ್ಷಿಣೆ",
        "btn_help": "💬 ಬೆಂಬಲ &amp; ಪ್ರತಿಕ್ರಿಯೆ",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "ml": {
        "greeting": "നമസ്കാരം, <b>{name}</b> 🙏",
        "schedule": "എല്ലാ ദിവസവും രാവിലെ <b>04:30 AM IST</b>-ന്, നിങ്ങളുടെ ദിവസം ശാന്തമായും ദൈവികമായും ആരംഭിക്കാൻ <b>ആശീർവാദത്തോടെ</b> ഒരു ദിവ്യ സന്ദേശം:",
        "b1": "• 🪔 ദൈനംദിന അനുഗ്രഹം + 🛕 ക്ഷേത്ര &amp; വിശേഷ അറിയിപ്പുകൾ",
        "b2": "• ⏳ ശുഭ സമയം",
        "b3": "• ✨ WoW [Words of Wisdom]",
        "b4": "• 🟡 സ്വർണ്ണം &amp; ⚪ വെള്ളി നിരക്കുകൾ",
        "b5": "• 🌦 കാലാവസ്ഥ [ദിവസ ആസൂത്രണം]",
        "step1": "<b>ഘട്ടം 1 / 3</b> — നിങ്ങളുടെ ജനനത്തീയതി നൽകുക (ഉദാ: <code>15-08-1985</code>):",
        "invalid_dob": "ദയവായി <code>DD-MM-YYYY</code> മാതൃകയിൽ ശരിയായ ജനനത്തീയതി നൽകുക (ഉദാ: <code>15-08-1985</code>):",
        "step2": (
            "<b>ഘട്ടം 2 / 3</b> — നിങ്ങളുടെ പ്രദേശവും നഗരവും നൽകുക (അല്ലെങ്കിൽ നഗരം മാത്രം):\n"
            "<i>ഉദാഹരണം: Ambattur, Chennai, Adyar, Chennai, അല്ലെങ്കിൽ Chennai\n"
            "എന്തുകൊണ്ട്? പ്രദേശം ചേർത്താൽ പ്രാദേശിക കാലാവസ്ഥയും മഴ വിവരവും കൂടുതൽ കൃത്യമാകും.</i>"
        ),
        "invalid_loc": "ദയവായി നിങ്ങളുടെ പ്രദേശവും നഗരവും നൽകുക (ഉദാ: <code>Adyar, Chennai</code>):",
        "step3": "<b>ഘട്ടം 3 / 3</b> — നിങ്ങളുടെ രാശി തിരഞ്ഞെടുക്കുക:",
        "back_lang": "← ഭാഷയിലേക്ക് മടങ്ങുക",
        "back_dob": "← ജനനത്തീയതിയിലേക്ക് മടങ്ങുക",
        "back_loc": "← പ്രദേശം / നഗരത്തിലേക്ക് മടങ്ങുക",
        "confirmed_title": "🙏 <b>സബ്സ്ക്രിപ്ഷൻ സ്ഥിരീകരിച്ചു — ആശീർവാദം സജീവം</b>",
        "lbl_lang": "ഭാഷ",
        "lbl_dob": "ജനനത്തീയതി",
        "lbl_loc": "പ്രദേശം / നഗരം",
        "lbl_rasi": "രാശി",
        "lbl_time": "ദിവസേന സമയം: <b>04:30 AM IST</b>",
        "footer_note": "/start വഴി വിവരങ്ങൾ മാറ്റാം അല്ലെങ്കിൽ /delete_data വഴി ഡാറ്റ നീക്കാം.",
        "btn_sample": "📨 ഇന്നത്തെ കാർഡ് ഇപ്പോൾ അയയ്ക്കുക",
        "btn_edit": "⚙️ മുൻഗണനകൾ മാറ്റുക",
        "btn_other": "✨ മറ്റ് സേവനങ്ങൾ",
        "btn_pay": "🙏 സഹായം / ദക്ഷിണ",
        "btn_help": "💬 സഹായവും പ്രതികരണവും",
        "btn_translate": "🌐 Translate [ENG]",
    },
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

DB_POOL: Optional[asyncpg.Pool] = None


def copy_for(lang: Optional[str]) -> dict:
    return WELCOME_COPY.get(lang or "en") or WELCOME_COPY["en"]


# ---------------------------------------------------------------------------
# Database Helpers (asyncpg)
# ---------------------------------------------------------------------------
async def get_db_pool() -> asyncpg.Pool:
    global DB_POOL
    if DB_POOL is None:
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


def parse_payload_dict(raw_payload) -> dict:
    if isinstance(raw_payload, dict):
        return raw_payload
    if isinstance(raw_payload, str):
        return json.loads(raw_payload)
    return {}


# ---------------------------------------------------------------------------
# Message Tracking & Cleanup Helpers
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


# ---------------------------------------------------------------------------
# UI Builders (Fully Localized Across All 6 Languages)
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


def build_welcome_dob_text(first_name: str, lang: str = "en") -> str:
    c = copy_for(lang)
    safe_name = first_name or "Friend"
    return (
        f"{CARD_HEADER}"
        f"{c['greeting'].format(name=safe_name)}\n\n"
        f"{c['schedule']}\n\n"
        f"{c['b1']}\n\n"
        f"{c['b2']}\n\n"
        f"{c['b3']}\n\n"
        f"{c['b4']}\n\n"
        f"{c['b5']}\n\n"
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


def build_rasi_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    c = copy_for(lang)
    rows = []
    for i in range(0, len(RASIS), 3):
        rows.append(
            [
                InlineKeyboardButton(label, callback_data=f"rasi:{code}")
                for code, label in RASIS[i : i + 3]
            ]
        )
    rows.append([InlineKeyboardButton(c["back_loc"], callback_data="back:location")])
    return InlineKeyboardMarkup(rows)


def build_daily_action_keyboard(telegram_id: int, lang: str, edition_date: str) -> InlineKeyboardMarkup:
    c = copy_for(lang)
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
            InlineKeyboardButton(c["btn_other"], callback_data="menu:other_services"),
            InlineKeyboardButton(c["btn_pay"], url=pay_url),
        ],
        [
            InlineKeyboardButton(c["btn_help"], url=support_url),
        ],
    ]
    if lang != "en":
        rows.append(
            [InlineKeyboardButton(c["btn_translate"], callback_data=f"translate:en:{edition_date}")]
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
    c = copy_for(lang_code)

    first_name = update.effective_user.first_name if update.effective_user else "Friend"
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(c["back_lang"], callback_data="back:lang")]]
    )
    await query.edit_message_text(
        build_welcome_dob_text(first_name, lang_code),
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
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
        rasi_label = dict(RASIS).get(rasi_code, rasi_code.title())

        user = update.effective_user
        telegram_id = user.id
        first_name = user.first_name or ""
        username = user.username or ""

        lang = context.user_data.get("lang", "en")
        c = copy_for(lang)
        lang_label = LANGUAGES.get(lang, "English")
        dob = context.user_data.get("dob", "Not set")
        locality = context.user_data.get("locality", "Chennai")

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
            f"✓ <b>{c['lbl_rasi']}:</b> {rasi_label}\n"
            f"✓ {c['lbl_time']}\n\n"
            f"{c['footer_note']}"
        )
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(c["btn_sample"], callback_data="send_sample_now")],
                [InlineKeyboardButton(c["btn_edit"], callback_data="back:lang")],
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
    lang = context.user_data.get("lang", "en")
    c = copy_for(lang)

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
            [[InlineKeyboardButton(c["back_lang"], callback_data="back:lang")]]
        )
        await query.edit_message_text(
            build_welcome_dob_text(first_name, lang),
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return DOB

    if target == "location":
        dob = context.user_data.get("dob", "")
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(c["back_dob"], callback_data="back:dob")]]
        )
        await query.edit_message_text(
            build_location_step_text(lang, dob),
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
    await query.answer()

    telegram_id = update.effective_user.id
    today_ist = datetime.now(IST).date()

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        sub = await conn.fetchrow("SELECT * FROM subscribers WHERE telegram_id = $1;", telegram_id)
        if not sub:
            await query.message.reply_text("Please complete /start setup first.")
            return
        rows = await conn.fetch(
            "SELECT bucket_type, bucket_key, payload FROM daily_shared_cache WHERE edition_date = $1;",
            today_ist,
        )

    lang = sub["preferred_language"] or "en"
    rasi = sub["rasi"] or "mesham"
    city = (sub["city"] or "chennai").lower()

    cache = {(r["bucket_type"], r["bucket_key"]): parse_payload_dict(r["payload"]) for r in rows}

    deity_block = (cache.get(("DEITY_DAY", "TODAY")) or {}).get(lang) or (
        cache.get(("DEITY_DAY", "TODAY")) or {}
    ).get("en", "🪔 <b>Daily Blessing:</b> Om Namah Shivaya")
    rasi_block = (cache.get(("RASI", rasi)) or {}).get(lang) or (
        cache.get(("RASI", rasi)) or {}
    ).get("en", "🌟 <b>Rasi Guidance:</b> Stay steady and focused today.")
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
    _, edition_date_str, score_str = query.data.split(":")
    score = int(score_str)
    edition_date = date.fromisoformat(edition_date_str)
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO message_ratings (telegram_id, edition_date, rating)
                VALUES ($1, $2, $3)
                ON CONFLICT (telegram_id, edition_date)
                DO UPDATE SET rating = EXCLUDED.rating;
                """,
                update.effective_user.id,
                edition_date,
                score,
            )
    except Exception as exc:
        logger.warning("Rating save skipped: %s", exc)
    await query.answer(f"Thank you for your {score}⭐ feedback!", show_alert=False)


async def translate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, _, edition_date_str = query.data.split(":")
    edition_date = date.fromisoformat(edition_date_str)
    telegram_id = update.effective_user.id

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        sub = await conn.fetchrow("SELECT * FROM subscribers WHERE telegram_id = $1;", telegram_id)
        rows = await conn.fetch(
            "SELECT bucket_type, bucket_key, payload FROM daily_shared_cache WHERE edition_date = $1;",
            edition_date,
        )

    rasi = (sub["rasi"] if sub else None) or "mesham"
    city = ((sub["city"] if sub else None) or "chennai").lower()
    cache = {(r["bucket_type"], r["bucket_key"]): parse_payload_dict(r["payload"]) for r in rows}

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
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM subscribers WHERE telegram_id = $1;", telegram_id)
    await update.message.reply_text(
        f"{CARD_HEADER}"
        "🗑️ Your profile and preferences have been permanently erased.\n"
        "You may re-subscribe anytime with /start.",
        parse_mode=ParseMode.HTML,
    )


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

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
