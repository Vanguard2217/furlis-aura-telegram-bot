import os
import csv
import io
import json
import asyncio
import logging
from datetime import datetime, date, timezone, timedelta
from typing import Dict, List

import aiohttp
import asyncpg

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("build_daily_cache")

DATABASE_URL = os.environ["DATABASE_URL"]
GOOGLE_SHEET_CSV_BASE_URL = os.environ.get("GOOGLE_SHEET_CSV_BASE_URL", "").strip()

IST = timezone(timedelta(hours=5, minutes=30))
EPOCH_ANCHOR_DATE = date(2026, 11, 25)

LANGS = ["en", "ta", "hi", "te", "kn", "ml"]

# ---------------------------------------------------------------------------
# 1. Built-in 7-Day Deity Mantra Cycle (Repeats Weekly MON -> SUN)
# ---------------------------------------------------------------------------
WEEKDAY_CODES = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

BUILT_IN_DEITY_7DAY: Dict[str, Dict[str, str]] = {
    "MON": {
        "en": "🪔 <b>Monday — Lord Shiva Blessing:</b>\n<i>Om Namah Shivaya</i> — May Lord Chandrashekhara bless your mind with stillness, clarity, and inner strength today.",
        "ta": "🪔 <b>திங்கள் — சிவபெருமான் அருள்:</b>\n<i>ஓம் நம சிவாய</i> — இன்று உங்கள் மனதில் அமைதியும் தெளிவும் ஆற்றலும் பெருகட்டும்.",
        "hi": "🪔 <b>सोमवार — भगवान शिव आशीर्वाद:</b>\n<i>ॐ नमः शिवाय</i> — आज आपका मन शांत, स्पष्ट और आत्मबल से परिपूर्ण रहे।",
        "te": "🪔 <b>సోమవారం — పరమశివుని ఆశీస్సులు:</b>\n<i>ఓం నమః శివాయ</i> — నేడు మీ మనస్సుకు ప్రశాంతత, స్పష్టత మరియు ఆత్మబలం కలగాలి.",
        "kn": "🪔 <b>ಸೋಮವಾರ — ಶಿವನ ಆಶೀರ್ವಾದ:</b>\n<i>ಓಂ ನಮಃ ಶಿವಾಯ</i> — ಇಂದು ನಿಮ್ಮ ಮನಸ್ಸಿಗೆ ಶಾಂತಿ, ಸ್ಪಷ್ಟತೆ ಮತ್ತು ಆತ್ಮಬಲ ದೊರೆಯಲಿ.",
        "ml": "🪔 <b>തിങ്കൾ — പരമശിവന്റെ അനുഗ്രഹം:</b>\n<i>ഓം നമഃ ശിവായ</i> — ഇന്ന് നിങ്ങളുടെ മനസ്സിന് സമാധാനവും വ്യക്തതയും ശക്തിയും ലഭിക്കട്ടെ.",
    },
    "TUE": {
        "en": "🪔 <b>Tuesday — Lord Murugan &amp; Hanuman Blessing:</b>\n<i>Om Saravanabhava • Om Hanumate Namaha</i> — May courage, protection, and decisive energy remove every obstacle in your path.",
        "ta": "🪔 <b>செவ்வாய் — முருகப்பெருமான் &amp; அனுமன் அருள்:</b>\n<i>ஓம் சரவணபவ</i> — துணிச்சலும் பாதுகாப்பும் வெற்றியும் இன்று உங்களுடன் இருக்கட்டும்.",
        "hi": "🪔 <b>मंगलवार — भगवान कार्तिकेय एवं हनुमान आशीर्वाद:</b>\n<i>ॐ हनुमते नमः</i> — साहस, सुरक्षा और सकारात्मक ऊर्जा आपके हर कार्य को सफल बनाए।",
        "te": "🪔 <b>మంగళవారం — సుబ్రహ్మణ్య స్వామి &amp; హనుమాన్ ఆశీస్సులు:</b>\n<i>ఓం శరవణభవ</i> — ధైర్యం, రక్షణ మరియు విజయం నేడు మీకు తోడుగా ఉండాలి.",
        "kn": "🪔 <b>ಮಂಗಳವಾರ — ಸುಬ್ರಹ್ಮಣ್ಯ &amp; ಹನುಮಾನ್ ಆಶೀರ್ವಾದ:</b>\n<i>ಓಂ ಶರವಣಭವ</i> — ಧೈರ್ಯ, ರಕ್ಷಣೆ ಮತ್ತು ಯಶಸ್ಸು ಇಂದು ನಿಮ್ಮದಾಗಲಿ.",
        "ml": "🪔 <b>ചൊവ്വ — സുബ്രഹ്മണ്യ സ്വാമി &amp; ഹനുമാൻ അനുഗ്രഹം:</b>\n<i>ഓം ശരവണഭവ</i> — ധൈര്യവും സംരക്ഷണവും വിജയവും ഇന്ന് നിങ്ങളോടൊപ്പം ഉണ്ടാകട്ടെ.",
    },
    "WED": {
        "en": "🪔 <b>Wednesday — Lord Vishnu &amp; Krishna Blessing:</b>\n<i>Om Namo Bhagavate Vasudevaya</i> — May wisdom, harmony, and prosperous progress guide every decision today.",
        "ta": "🪔 <b>புதன் — ஸ்ரீமன் நாராயணன் &amp; கிருஷ்ணர் அருள்:</b>\n<i>ஓம் நமோ பகவதே வாசுதேவாய</i> — விவேகமும் நல்லிணக்கமும் வளமும் இன்று உங்களை வழிநடத்தட்டும்.",
        "hi": "🪔 <b>बुधवार — भगवान विष्णु एवं श्रीकृष्ण आशीर्वाद:</b>\n<i>ॐ नमो भगवते वासुदेवाय</i> — विवेक, सामंजस्य और समृद्धि आज आपके हर निर्णय का मार्गदर्शन करे।",
        "te": "🪔 <b>బుధవారం — శ్రీ మహావిష్ణువు &amp; శ్రీకృష్ణుని ఆశీస్సులు:</b>\n<i>ఓం నమో భగవతే వాసుదేవాయ</i> — వివేకం, సామరస్యం మరియు శ్రేయస్సు నేడు మిమ్మల్ని నడిపించాలి.",
        "kn": "🪔 <b>ಬುಧವಾರ — ಶ್ರೀ ಮಹಾವಿಷ್ಣು &amp; ಶ್ರೀಕೃಷ್ಣನ ಆಶೀರ್ವಾದ:</b>\n<i>ಓಂ ನಮೋ ಭಗವತೇ ವಾಸುದೇವಾಯ</i> — ವಿವೇಕ, ಸಾಮರಸ್ಯ ಮತ್ತು ಸಮೃದ್ಧಿ ಇಂದು ನಿಮ್ಮನ್ನು ಮುನ್ನಡೆಸಲಿ.",
        "ml": "🪔 <b>ബുധൻ — മഹാവിഷ്ണു &amp; ശ്രീകൃഷ്ണ അനുഗ്രഹം:</b>\n<i>ഓം നമോ ഭഗവതേ വാസുദേവായ</i> — വിവേകവും ഐക്യവും ഐശ്വര്യവും ഇന്ന് നിങ്ങളെ നയിക്കട്ടെ.",
    },
    "THU": {
        "en": "🪔 <b>Thursday — Sri Dakshinamurthy &amp; Guru Blessing:</b>\n<i>Om Gurave Namaha</i> — May divine grace illuminate your intellect and bring wise counsel into your day.",
        "ta": "🪔 <b>வியாழன் — ஸ்ரீ தட்சிணாமூர்த்தி &amp; குரு அருள்:</b>\n<i>ஓம் குரவே நமஹ</i> — தெய்வீக அருள் உங்கள் அறிவையும் நல்வழியையும் ஒளிரச் செய்யட்டும்.",
        "hi": "🪔 <b>गुरुवार — श्री दक्षिणामूर्ति एवं गुरु आशीर्वाद:</b>\n<i>ॐ गुरवे नमः</i> — गुरु कृपा से आपकी बुद्धि प्रकाशित हो और हर कार्य में शुभता आए।",
        "te": "🪔 <b>గురువారం — శ్రీ దక్షిణామూర్తి &amp; గురు ఆశీస్సులు:</b>\n<i>ఓం గురవే నమః</i> — గురు కృపతో మీ బుద్ధి వికసించి శుభ ఫలితాలు కలగాలి.",
        "kn": "🪔 <b>ಗುರುವಾರ — ಶ್ರೀ ದಕ್ಷಿಣಾಮೂರ್ತಿ &amp; ಗುರು ಆಶೀರ್ವಾದ:</b>\n<i>ಓಂ ಗುರವೇ ನಮಃ</i> — ಗುರು ಕೃಪೆಯಿಂದ ನಿಮ್ಮ ಬುದ್ಧಿ ಪ್ರಕಾಶಿಸಿ ಶುಭವಾಗಲಿ.",
        "ml": "🪔 <b>വ്യാഴം — ശ്രീ ദക്ഷിണാമൂർത്തി &amp; ഗുരു അനുഗ്രഹം:</b>\n<i>ഓം ഗുരവേ നമഃ</i> — ഗുരു കൃപയാൽ നിങ്ങളുടെ ബുദ്ധി പ്രകാശിക്കട്ടെ.",
    },
    "FRI": {
        "en": "🪔 <b>Friday — Goddess Mahalakshmi &amp; Parashakti Blessing:</b>\n<i>Om Shreem Mahalakshmyai Namaha</i> — May abundance, grace, and family well-being fill your home today.",
        "ta": "🪔 <b>வெள்ளி — ஸ்ரீ மகாலட்சுமி &amp; பராசக்தி அருள்:</b>\n<i>ஓம் ஸ்ரீம் மகாலட்சுமியை நமஹ</i> — ஐஸ்வர்யமும் அருளும் குடும்ப நலமும் இன்று உங்கள் இல்லத்தில் நிறையட்டும்.",
        "hi": "🪔 <b>शुक्रवार — माँ महालक्ष्मी एवं पराशक्ति आशीर्वाद:</b>\n<i>ॐ श्रीं महालक्ष्म्यै नमः</i> — सुख, समृद्धि और सौभाग्य से आपका घर-आँगन आलोकित रहे।",
        "te": "🪔 <b>శుక్రవారం — శ్రీ మహాలక్ష్మి &amp; పరాశక్తి ఆశీస్సులు:</b>\n<i>ఓం శ్రీం మహాలక్ష్మ్యై నమః</i> — ఐశ్వర్యం, అనుగ్రహం మరియు కుటుంబ సౌభాగ్యం నేడు మీ ఇంట వెల్లివిరియాలి.",
        "kn": "🪔 <b>ಶುಕ್ರವಾರ — ಶ್ರೀ ಮಹಾಲಕ್ಷ್ಮಿ &amp; ಪರಾಶಕ್ತಿ ಆಶೀರ್ವಾದ:</b>\n<i>ಓಂ ಶ್ರೀಂ ಮಹಾಲಕ್ಷ್ಮ್ಯೈ ನಮಃ</i> — ಐಶ್ವರ್ಯ, ಅನುಗ್ರಹ ಮತ್ತು ಕುಟುಂಬದ ಸೌಭಾಗ್ಯ ಇಂದು ನಿಮ್ಮದಾಗಲಿ.",
        "ml": "🪔 <b>വെള്ളി — ശ്രീ മഹാലക്ഷ്മി &amp; പരാശക്തി അനുഗ്രഹം:</b>\n<i>ഓം ശ്രീം മഹാലക്ഷ്മ്യൈ നമഃ</i> — ഐശ്വര്യവും അനുഗ്രഹവും കുടുംബസൗഖ്യവും ഇന്ന് നിങ്ങളുടെ ഭവനത്തിൽ നിറയട്ടെ.",
    },
    "SAT": {
        "en": "🪔 <b>Saturday — Lord Venkateswara (Thirumal) Blessing:</b>\n<i>Om Namo Venkatesaya</i> — May Govinda's compassion steady your efforts and bless your perseverance with lasting peace.",
        "ta": "🪔 <b>சனி — ஸ்ரீ வெங்கடேசப் பெருமாள் அருள்:</b>\n<i>ஓம் நமோ வெங்கடேசாய</i> — ஏழுமலையானின் கருணை உங்கள் முயற்சிகளுக்கு நிலையான வெற்றியையும் அமைதியையும் தரட்டும்.",
        "hi": "🪔 <b>शनिवार — भगवान वेंकटेश्वर (तिरुमल) आशीर्वाद:</b>\n<i>ॐ नमो वेंकटेशाय</i> — प्रभु गोविंद की कृपा आपके परिश्रम को स्थिरता और शांति प्रदान करे।",
        "te": "🪔 <b>శనివారం — శ్రీ వేంకటేశ్వర స్వామి ఆశీస్సులు:</b>\n<i>ఓం నమో వేంకటేశాయ</i> — శ్రీనివాసుని కరుణ మీ ప్రయత్నాలకు స్థిరమైన విజయాన్ని, శాంతిని ఇవ్వాలి.",
        "kn": "🪔 <b>ಶನಿವಾರ — ಶ್ರೀ ವೆಂಕಟೇಶ್ವರ ಸ್ವಾಮಿ ಆಶೀರ್ವಾದ:</b>\n<i>ಓಂ ನಮೋ ವೆಂಕಟೇಶಾಯ</i> — ಶ್ರೀನಿವಾಸನ ಕರುಣೆ ನಿಮ್ಮ ಪ್ರಯತ್ನಗಳಿಗೆ ಸ್ಥಿರವಾದ ಯಶಸ್ಸು ಮತ್ತು ಶಾಂತಿಯನ್ನು ನೀಡಲಿ.",
        "ml": "🪔 <b>ശനി — ശ്രീ വെങ്കടേശ്വര സ്വാമി അനുഗ്രഹം:</b>\n<i>ഓം നമോ വെങ്കടേശായ</i> — ഭഗവാൻ ശ്രീനിവാസന്റെ കരുണ നിങ്ങളുടെ പരിശ്രമങ്ങൾക്ക് വിജയവും സമാധാനവും നൽകട്ടെ.",
    },
    "SUN": {
        "en": "🪔 <b>Sunday — Lord Surya Narayana Blessing:</b>\n<i>Om Suryaya Namaha</i> — May the radiant grace of Surya Narayana bless you with vitality, good health, and clarity.",
        "ta": "🪔 <b>ஞாயிறு — ஸ்ரீ சூரிய நாராயணர் அருள்:</b>\n<i>ஓம் சூர்யாய நமஹ</i> — சூரிய பகவானின் அருள் உங்களுக்கு ஆரோக்கியமும் புத்துணர்ச்சியும் தெளிவும் தரட்டும்.",
        "hi": "🪔 <b>रविवार — भगवान सूर्यनारायण आशीर्वाद:</b>\n<i>ॐ सूर्याय नमः</i> — भगवान सूर्य की तेजस्वी कृपा आपको उत्तम स्वास्थ्य, ऊर्जा और स्पष्टता प्रदान करे।",
        "te": "🪔 <b>ఆదివారం — శ్రీ సూర్యనారాయణ స్వామి ఆశీస్సులు:</b>\n<i>ఓం సూర్యాయ నమః</i> — సూర్య భగవానుని అనుగ్రహం మీకు ఆరోగ్యం, తేజస్సు మరియు స్పష్టతను ప్రసాదించాలి.",
        "kn": "🪔 <b>ಭಾನುವಾರ — ಶ್ರೀ ಸೂರ್ಯನಾರಾಯಣ ಸ್ವಾಮಿ ಆಶೀರ್ವಾದ:</b>\n<i>ಓಂ ಸೂರ್ಯಾಯ ನಮಃ</i> — ಸೂರ್ಯ ಭಗವಾನನ ಕೃಪೆ ನಿಮಗೆ ಆರೋಗ್ಯ, ಚೈತನ್ಯ ಮತ್ತು ಸ್ಪಷ್ಟತೆಯನ್ನು ನೀಡಲಿ.",
        "ml": "🪔 <b>ഞായർ — ശ്രീ സൂര്യനാരായണ സ്വാമി അനുഗ്രഹം:</b>\n<i>ഓം സൂര്യായ നമഃ</i> — സൂര്യഭഗവാന്റെ അനുഗ്രഹം നിങ്ങൾക്ക് ആരോഗ്യവും ഉന്മേഷവും വ്യക്തതയും നൽകട്ടെ.",
    },
}

# ---------------------------------------------------------------------------
# 2. Built-in Scripture Bank (Bhagavad Gita, Upanishads & Vedas)
# ---------------------------------------------------------------------------
BUILT_IN_SCRIPTURE_QUOTES: List[Dict[str, str]] = [
    {
        "source": "Bhagavad Gita (2.47)",
        "en": "You have a right to perform your prescribed duty, but never to the fruits of action.",
        "ta": "கடமையைச் செய்வதற்கே உனக்கு அதிகாரம் உண்டு; அதன் பலன்களில் ஒருபோதும் இல்லை.",
        "hi": "कर्म करने में ही तुम्हारा अधिकार है, उसके फलों में कभी नहीं।",
        "te": "నీ విధిని నిర్వర్తించే హక్కు మాత్రమే నీకు ఉంది, ఫలితాలపై ఎన్నడూ లేదు.",
        "kn": "ನಿನ್ನ ಕರ್ತವ್ಯವನ್ನು ಮಾಡಲು ಮಾತ್ರ ನಿನಗೆ ಹಕ್ಕಿದೆ, ಅದರ ಫಲಗಳ ಮೇಲೆ ಎಂದಿಗೂ ಇಲ್ಲ.",
        "ml": "കർമ്മം ചെയ്യാൻ മാത്രമേ നിനക്ക് അധികാരമുള്ളൂ, അതിന്റെ ഫലങ്ങളിലൊരിക്കലുമില്ല.",
    },
    {
        "source": "Katha Upanishad (1.3.14)",
        "en": "Arise, awake, and stop not till the goal is reached.",
        "ta": "எழுமின், விழிமின், குறிக்கோளை அடையும் வரை நில்லாதீர்.",
        "hi": "उठो, जागो और तब तक मत रुको जब तक लक्ष्य की प्राप्ति न हो जाए।",
        "te": "లెండి, మేల్కొనండి, గమ్యం చేరే వరకు ఆగకండి.",
        "kn": "ಏಳಿ, ಎಚ್ಚರಗೊಳ್ಳಿ, ಗುರಿ ತಲುಪುವವರೆಗೆ ನಿಲ್ಲದಿರಿ.",
        "ml": "ഉണരുക, എഴുന്നേൽക്കുക, ലക്ഷ്യത്തിലെത്തുന്നതുവരെ വിശ്രമിക്കാതിരിക്കുക.",
    },
    {
        "source": "Rigveda (1.89.1)",
        "en": "Let noble thoughts come to us from every side of the universe.",
        "ta": "எல்லா திசைகளிலிருந்தும் உயரிய எண்ணங்கள் நம்மை வந்தடையட்டும்.",
        "hi": "हमें चारों दिशाओं से श्रेष्ठ और कल्याणकारी विचार प्राप्त हों।",
        "te": "అన్ని వైపుల నుండి ఉన్నతమైన ఆలోచనలు మనకు కలగాలి.",
        "kn": "ಎಲ್ಲಾ ದಿಕ್ಕುಗಳಿಂದಲೂ ಶ್ರೇಷ್ಠವಾದ ಆಲೋಚನೆಗಳು ನಮಗೆ ಬರಲಿ.",
        "ml": "എല്ലാ ദിക്കുകളിൽ നിന്നും ശ്രേഷ്ഠമായ ചിന്തകൾ നമ്മിലേക്ക് വരട്ടെ.",
    },
    {
        "source": "Bhagavad Gita (6.5)",
        "en": "Elevate yourself through the power of your own mind, and never degrade yourself.",
        "ta": "உன் மனதின் வலிமையால் உன்னை உயர்த்திக் கொள்; ஒருபோதும் உன்னைத் தாழ்த்திக் கொள்ளாதே.",
        "hi": "अपने मन की शक्ति से अपना उद्धार स्वयं करें, स्वयं को कभी नीचे न गिरने दें।",
        "te": "నీ మనస్సు శక్తితో నిన్ను నీవు ఉద్ధరించుకో, ఎన్నడూ నిన్ను నీవు తగ్గించుకోకు.",
        "kn": "ನಿನ್ನ ಮನಸ್ಸಿನ ಶಕ್ತಿಯಿಂದ ನಿನ್ನನ್ನು ನೀನೇ ಉದ್ಧರಿಸಿಕೋ, ಎಂದಿಗೂ ಕುಗ್ಗಬೇಡ.",
        "ml": "നിന്റെ മനസ്സിന്റെ ശക്തിയാൽ നിന്നെത്തന്നെ ഉയർത്തുക, ഒരിക്കലും തളരാതിരിക്കുക.",
    },
    {
        "source": "Brihadaranyaka Upanishad (1.3.28)",
        "en": "Lead me from the unreal to the real, from darkness to light, from death to immortality.",
        "ta": "பொய்மையிலிருந்து மெய்மைக்கும், இருளிலிருந்து ஒளிக்கும் என்னை வழிநடத்துவாயாக.",
        "hi": "हमें असत्य से सत्य की ओर, अंधकार से प्रकाश की ओर ले चलो।",
        "te": "అసత్యం నుండి సత్యం వైపు, చీకటి నుండి వెలుగు వైపు నడిపించు.",
        "kn": "ಅಸತ್ಯದಿಂದ ಸತ್ಯದತ್ತ, ಕತ್ತಲೆಯಿಂದ ಬೆಳಕಿನತ್ತ ನಮ್ಮನ್ನು ನಡೆಸು.",
        "ml": "അസത്യത്തിൽ നിന്ന് സത്യത്തിലേക്കും ഇരുട്ടിൽ നിന്ന് വെളിച്ചത്തിലേക്കും നയിക്കേണമേ.",
    },
    {
        "source": "Isha Upanishad (1)",
        "en": "All this universe is pervaded by the Divine; enjoy what is given with detachment and gratitude.",
        "ta": "இப்பிரபஞ்சம் முழுவதும் இறைவனால் நிறைந்துள்ளது; நன்றியுடனும் பற்றற்ற மனதுடனும் வாழ்க.",
        "hi": "यह संपूर्ण ब्रह्मांड ईश्वर से व्याप्त है; कृतज्ञता और अनासक्ति के साथ जीवन जिएं।",
        "te": "ఈ విశ్వమంతా దైవంతో నిండి ఉంది; కృతజ్ఞతతో, నిస్వార్థంగా జీవించండి.",
        "kn": "ಈ ಇಡೀ ವಿಶ್ವವು ದೈವದಿಂದ ವ್ಯಾಪಿಸಿದೆ; ಕೃತಜ್ಞತೆಯಿಂದ ಜೀವಿಸಿ.",
        "ml": "ഈ പ്രപഞ്ചമെല്ലാം ഈശ്വരനാൽ നിറഞ്ഞിരിക്കുന്നു; കൃതജ്ഞതയോടെ ജീവിക്കുക.",
    },
    {
        "source": "Yajurveda (36.17)",
        "en": "May there be peace in the heavens, peace in the atmosphere, and peace upon the earth.",
        "ta": "விண்ணிலும், காற்றிலும், மண்ணிலும் அமைதி நிலவட்டும்.",
        "hi": "अंतरिक्ष में शांति हो, पृथ्वी पर शांति हो, सर्वत्र शांति का वास हो।",
        "te": "ఆకాశంలో, వాతావరణంలో మరియు భూమిపై శాంతి నెలకొనాలి.",
        "kn": "ಆಕಾಶದಲ್ಲಿ, ವಾತಾವರಣದಲ್ಲಿ ಮತ್ತು ಭೂಮಿಯ ಮೇಲೆ ಶಾಂತಿ ನೆಲೆಸಲಿ.",
        "ml": "ആകാശത്തും അന്തരീക്ഷത്തിലും ഭൂമിയിലും സമാധാനം നിലനിൽക്കട്ടെ.",
    },
]

QUOTE_HEADERS = {
    "en": "🌟 <b>Quote:</b>",
    "ta": "🌟 <b>பொன்மொழி:</b>",
    "hi": "🌟 <b>अनमोल वचन:</b>",
    "te": "🌟 <b>సూక్తి:</b>",
    "kn": "🌟 <b>ನುಡಿಮುತ್ತು:</b>",
    "ml": "🌟 <b>സന്ദേശം:</b>",
}

WOW_HEADERS = {
    "en": "✨ <b>WoW [Words of Wisdom]:</b>",
    "ta": "✨ <b>WoW [ஞான மொழிகள்]:</b>",
    "hi": "✨ <b>WoW [ज्ञान की बातें]:</b>",
    "te": "✨ <b>WoW [జ్ఞాన వాక్కులు]:</b>",
    "kn": "✨ <b>WoW [ಜ್ಞಾನದ ಮಾತುಗಳು]:</b>",
    "ml": "✨ <b>WoW [ജ്ഞാനവാക്കുകൾ]:</b>",
}

RASI_DISPLAY_NAMES: Dict[str, Dict[str, str]] = {
    "mesham": {"en": "Mesham", "ta": "மேஷம்", "hi": "मेष", "te": "మేషం", "kn": "ಮೇಷ", "ml": "മേടം"},
    "rishabam": {"en": "Rishabam", "ta": "ரிஷபம்", "hi": "वृषभ", "te": "వృషభం", "kn": "ವೃಷಭ", "ml": "ഇടവം"},
    "mithunam": {"en": "Mithunam", "ta": "மிதுனம்", "hi": "मिथुन", "te": "మిథునం", "kn": "ಮಿಥುನ", "ml": "മിഥുനം"},
    "kadagam": {"en": "Kadagam", "ta": "கடகம்", "hi": "कर्क", "te": "కర్కాటకం", "kn": "ಕಟಕ", "ml": "കർക്കിടകം"},
    "simmam": {"en": "Simmam", "ta": "சிம்மம்", "hi": "सिंह", "te": "సింహం", "kn": "ಸಿಂಹ", "ml": "ചിങ്ങം"},
    "kanni": {"en": "Kanni", "ta": "கன்னி", "hi": "कन्या", "te": "కన్య", "kn": "ಕನ್ಯಾ", "ml": "കന്നി"},
    "thulam": {"en": "Thulam", "ta": "துலாம்", "hi": "तुला", "te": "తుల", "kn": "ತುಲಾ", "ml": "തുലാം"},
    "vrischikam": {"en": "Vrischikam", "ta": "விருச்சிகம்", "hi": "वृश्चिक", "te": "వృశ్చికం", "kn": "ವೃಶ್ಚಿಕ", "ml": "വൃശ്ചികം"},
    "dhanusu": {"en": "Dhanusu", "ta": "தனுசு", "hi": "धनु", "te": "ధనుస్సు", "kn": "ಧನುಸ್ಸು", "ml": "ധനു"},
    "magaram": {"en": "Magaram", "ta": "மகரம்", "hi": "मकर", "te": "మకరం", "kn": "ಮಕರ", "ml": "മകരം"},
    "kumbam": {"en": "Kumbam", "ta": "கும்பம்", "hi": "कुंभ", "te": "కుంభం", "kn": "ಕುಂಭ", "ml": "കുംഭം"},
    "meenam": {"en": "Meenam", "ta": "மீனம்", "hi": "मीन", "te": "మీనం", "kn": "ಮೀನ", "ml": "മീനം"},
}

WOW_LOCALIZED_BODIES: Dict[str, str] = {
    "en": (
        "• <b>{rasi} — 3 Positives Today:</b>\n"
        "1. Clear focus on key priorities\n"
        "2. Supportive conversations with family &amp; peers\n"
        "3. Steady progress through patient effort"
    ),
    "ta": (
        "• <b>{rasi} — இன்றைய 3 நற்பலன்கள்:</b>\n"
        "1. முக்கியப் பணிகளில் தெளிவான கவனம்\n"
        "2. குடும்பத்தினர் மற்றும் சக ஊழியர்களின் ஆதரவு\n"
        "3. பொறுமையான முயற்சியால் நிலையான முன்னேற்றம்"
    ),
    "hi": (
        "• <b>{rasi} — आज के 3 सकारात्मक संकेत:</b>\n"
        "1. प्रमुख कार्यों पर स्पष्ट ध्यान\n"
        "2. परिवार और सहकर्मियों से सहयोगपूर्ण संवाद\n"
        "3. धैर्यपूर्ण प्रयास से निरंतर प्रगति"
    ),
    "te": (
        "• <b>{rasi} — నేటి 3 శుభ ఫలితాలు:</b>\n"
        "1. ముఖ్యమైన పనులపై స్పష్టమైన దృష్టి\n"
        "2. కుటుంబం మరియు సహచరులతో సానుకూల సంభాషణలు\n"
        "3. ఓర్పుతో కూడిన ప్రయత్నంతో స్థిరమైన పురోగతి"
    ),
    "kn": (
        "• <b>{rasi} — ಇಂದಿನ 3 ಸಕಾರಾತ್ಮಕ ಅಂಶಗಳು:</b>\n"
        "1. ಪ್ರಮುಖ ಕೆಲಸಗಳ ಮೇಲೆ ಸ್ಪಷ್ಟ ಗಮನ\n"
        "2. ಕುಟುಂಬ ಮತ್ತು ಸಹೋದ್ಯೋಗಿಗಳೊಂದಿಗೆ ಉತ್ತಮ ಮಾತುಕತೆ\n"
        "3. ತಾಳ್ಮೆಯ ಪ್ರಯತ್ನದಿಂದ ಸ್ಥಿರ ಪ್ರಗತಿ"
    ),
    "ml": (
        "• <b>{rasi} — ഇന്നത്തെ 3 അനുകൂല ഫലങ്ങൾ:</b>\n"
        "1. പ്രധാന കാര്യങ്ങളിൽ വ്യക്തമായ ശ്രദ്ധ\n"
        "2. കുടുംബാംഗങ്ങളുമായും സഹപ്രവർത്തകരുമായും സൗഹാർദ്ദപരമായ ആശയവിനിമയം\n"
        "3. ക്ഷമയോടെയുള്ള പരിശ്രമത്തിലൂടെ സ്ഥിരമായ പുരോഗതി"
    ),
}

# ---------------------------------------------------------------------------
# 3. Gold & Silver Rates ([As of DATE])
# ---------------------------------------------------------------------------
def compute_bullion_as_of_date(now_ist: datetime) -> str:
    d = now_ist.date()
    if now_ist.hour < 10:
        d = d - timedelta(days=1)
    if d.weekday() == 6:
        d = d - timedelta(days=1)
    return d.strftime("%d %b %Y")


def build_bullion_payload(now_ist: datetime) -> Dict[str, str]:
    as_of_str = compute_bullion_as_of_date(now_ist)
    g22 = "₹7,140/g"
    g24 = "₹7,789/g"
    silver = "₹91.50/g"

    return {
        "en": f"🟡 <b>Gold Rate ⚪️ Silver Rate [As of {as_of_str}]:</b>\n22K: {g22}  |  24K: {g24}  |  ⚪️ Silver: {silver}",
        "ta": f"🟡 <b>தங்கம் விலை ⚪️ வெள்ளி விலை [{as_of_str} நிலவரப்படி]:</b>\n22K: {g22}  |  24K: {g24}  |  ⚪️ வெள்ளி: {silver}",
        "hi": f"🟡 <b>सोना भाव ⚪️ चांदी भाव [{as_of_str} तक]:</b>\n22K: {g22}  |  24K: {g24}  |  ⚪️ चांदी: {silver}",
        "te": f"🟡 <b>బంగారం ధర ⚪️ వెండి ధర [{as_of_str} నాటికి]:</b>\n22K: {g22}  |  24K: {g24}  |  ⚪️ వెండి: {silver}",
        "kn": f"🟡 <b>ಚಿನ್ನ ದರ ⚪️ ಬೆಳ್ಳಿ ದರ [{as_of_str} ರಂತೆ]:</b>\n22K: {g22}  |  24K: {g24}  |  ⚪️ ಬೆಳ್ಳಿ: {silver}",
        "ml": f"🟡 <b>സ്വർണ്ണ നിരക്ക് ⚪️ വെള്ളി നിരക്ക് [{as_of_str} പ്രകാരം]:</b>\n22K: {g22}  |  24K: {g24}  |  ⚪️ വെള്ളി: {silver}",
    }


# ---------------------------------------------------------------------------
# 4. Async Google Sheet CSV Reader (Plug-and-Play When Ready)
# ---------------------------------------------------------------------------
async def fetch_sheet_rows(session: aiohttp.ClientSession, tab_name: str) -> List[Dict[str, str]]:
    if not GOOGLE_SHEET_CSV_BASE_URL:
        return []
    try:
        url = f"{GOOGLE_SHEET_CSV_BASE_URL}&sheet={tab_name}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            resp.raise_for_status()
            text = await resp.text()
            return list(csv.DictReader(io.StringIO(text)))
    except Exception as exc:
        logger.warning("Sheet tab '%s' unavailable (%s); using built-in bank.", tab_name, exc)
        return []


async def select_today_deity(session: aiohttp.ClientSession, today_ist: date) -> Dict[str, str]:
    day_code = WEEKDAY_CODES[today_ist.weekday()]
    sheet_rows = await fetch_sheet_rows(session, "Rasi_Deity_Templates")
    for row in sheet_rows:
        if (row.get("template_type") or "").strip().upper() == "DEITY_DAY" and (
            row.get("key_code") or ""
        ).strip().upper() == day_code:
            return {
                lang: f"🪔 <b>{row.get(f'title_{lang}') or row.get('title_en', 'Daily Blessing')}:</b>\n{row.get(f'body_{lang}') or row.get('body_en', '')}"
                for lang in LANGS
            }
    return BUILT_IN_DEITY_7DAY[day_code]


async def select_today_scripture(session: aiohttp.ClientSession, today_ist: date) -> Dict[str, str]:
    sheet_rows = [
        r
        for r in await fetch_sheet_rows(session, "Quotes_Bank")
        if (r.get("active_flag") or "TRUE").strip().upper() == "TRUE"
    ]
    day_offset = max(0, (today_ist - EPOCH_ANCHOR_DATE).days)

    if sheet_rows:
        chosen = sheet_rows[day_offset % len(sheet_rows)]
        src = chosen.get("citation") or chosen.get("scripture_source") or "Sacred Scripture"
        return {
            lang: (
                f"{QUOTE_HEADERS[lang]}\n"
                f"\"{(chosen.get(f'{lang}_translation') or chosen.get('en_translation', '')).strip()}\" "
                f"— <i>{src}</i>"
            )
            for lang in LANGS
        }

    chosen = BUILT_IN_SCRIPTURE_QUOTES[day_offset % len(BUILT_IN_SCRIPTURE_QUOTES)]
    src = chosen["source"]
    return {
        lang: f"{QUOTE_HEADERS[lang]}\n\"{chosen.get(lang) or chosen['en']}\" — <i>{src}</i>"
        for lang in LANGS
    }


def build_wow_defaults() -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for rasi, rasi_labels in RASI_DISPLAY_NAMES.items():
        out[rasi] = {
            lang: f"{WOW_HEADERS[lang]}\n{WOW_LOCALIZED_BODIES[lang].format(rasi=rasi_labels[lang])}"
            for lang in LANGS
        }
    return out


# ---------------------------------------------------------------------------
# Main Async Cache Builder
# ---------------------------------------------------------------------------
async def main() -> None:
    now_ist = datetime.now(IST)
    today_ist = now_ist.date()
    logger.info("Building daily_shared_cache for %s IST", today_ist)

    async with aiohttp.ClientSession() as session:
        deity_payload = await select_today_deity(session, today_ist)
        quote_payload = await select_today_scripture(session, today_ist)

    bullion_payload = build_bullion_payload(now_ist)
    wow_map = build_wow_defaults()

    auspicious_chennai = {
        "en": (
            "⏰ <b>Auspicious Timing [Plan Your Decisions]:</b>\n"
            "• Nalla Neram: 07:45 AM – 08:45 AM | 04:45 PM – 05:45 PM\n"
            "• Rahukalam: 12:00 PM – 01:30 PM"
        ),
        "ta": (
            "⏰ <b>நல்ல நேரம் [உங்கள் முடிவுகளைத் திட்டமிடுங்கள்]:</b>\n"
            "• நல்ல நேரம்: 07:45 AM – 08:45 AM | 04:45 PM – 05:45 PM\n"
            "• ராகு காலம்: 12:00 PM – 01:30 PM"
        ),
        "hi": (
            "⏰ <b>शुभ समय [अपने निर्णयों की योजना बनाएं]:</b>\n"
            "• शुभ मुहूर्त: 07:45 AM – 08:45 AM | 04:45 PM – 05:45 PM\n"
            "• राहुकाल: 12:00 PM – 01:30 PM"
        ),
        "te": (
            "⏰ <b>శుభ సమయం [మీ నిర్ణయాలను ప్రణాళిక చేయండి]:</b>\n"
            "• శుభ సమయం: 07:45 AM – 08:45 AM | 04:45 PM – 05:45 PM\n"
            "• రాహుకాలం: 12:00 PM – 01:30 PM"
        ),
        "kn": (
            "⏰ <b>ಶುಭ ಸಮಯ [ನಿಮ್ಮ ನಿರ್ಧಾರಗಳನ್ನು ಯೋಜಿಸಿ]:</b>\n"
            "• ಶುಭ ಸಮಯ: 07:45 AM – 08:45 AM | 04:45 PM – 05:45 PM\n"
            "• ರಾಹುಕಾಲ: 12:00 PM – 01:30 PM"
        ),
        "ml": (
            "⏰ <b>ശുഭ സമയം [തീരുമാനങ്ങൾ ആസൂത്രണം ചെയ്യുക]:</b>\n"
            "• ശുഭ സമയം: 07:45 AM – 08:45 AM | 04:45 PM – 05:45 PM\n"
            "• രാഹുകാലം: 12:00 PM – 01:30 PM"
        ),
    }
    weather_chennai = {
        "en": "🌦 <b>Weather [Plan Your Day]:</b>\n27°C • Partly cloudy morning, light coastal breeze",
        "ta": "🌦 <b>வானிலை [உங்கள் நாளைத் திட்டமிடுங்கள்]:</b>\n27°C • லேசான மேகமூட்டத்துடன் இனிமையான காலை தென்றல்",
        "hi": "🌦 <b>मौसम [दिन की योजना]:</b>\n27°C • हल्के बादल और सुहावनी सुबह की हवा",
        "te": "🌦 <b>వాతావరణం [రోజు ప్రణాళిక]:</b>\n27°C • పాక్షిక మేఘావృతమైన ఉదయం, తేలికపాటి గాలి",
        "kn": "🌦 <b>ಹವಾಮಾನ [ದಿನದ ಯೋಜನೆ]:</b>\n27°C • ಭಾಗಶಃ ಮೋಡ ಕವಿದ ಮುಂಜಾನೆ, ತಂಪಾದ ಗಾಳಿ",
        "ml": "🌦 <b>കാലാവസ്ഥ [ദിവസ ആസൂത്രണം]:</b>\n27°C • ഭാഗികമായി മേഘാവൃതമായ പ്രഭാതം, ഇളം കാറ്റ്",
    }

    records = [
        (today_ist, "DEITY_DAY", "TODAY", json.dumps(deity_payload)),
        (today_ist, "QUOTE", "TODAY", json.dumps(quote_payload)),
        (today_ist, "GOLD_INR", "INDIA", json.dumps(bullion_payload)),
        (today_ist, "AUSPICIOUS", "chennai", json.dumps(auspicious_chennai)),
        (today_ist, "WEATHER", "chennai", json.dumps(weather_chennai)),
    ]
    for rasi_key, payload in wow_map.items():
        records.append((today_ist, "RASI", rasi_key, json.dumps(payload)))

    conn = await asyncpg.connect(dsn=DATABASE_URL)
    try:
        for edition_dt, b_type, b_key, payload_json in records:
            await conn.execute(
                """
                INSERT INTO daily_shared_cache (edition_date, bucket_type, bucket_key, payload)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (edition_date, bucket_type, bucket_key)
                DO UPDATE SET payload = EXCLUDED.payload, created_at = NOW();
                """,
                edition_dt,
                b_type,
                b_key,
                payload_json,
            )
    finally:
        await conn.close()

    logger.info("Successfully cached %d shared buckets for %s", len(records), today_ist)


if __name__ == "__main__":
    asyncio.run(main())
