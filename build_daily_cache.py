# build_daily_cache.py — AURA Daily Cache Builder (Localized + Deity-Matched 2-Sentence Verse + Single Scripture Rotation)
import os
import re
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
SUPPORTED_LANGS = ("en", "ta", "hi", "te", "kn", "ml")

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
    45: "Foggy", 48: "Dense Fog", 51: "Light Drizzle", 53: "Moderate Drizzle",
    61: "Light Rain", 63: "Moderate Rain", 65: "Heavy Rain",
    71: "Light Snow", 73: "Moderate Snow", 75: "Heavy Snow",
    80: "Rain Showers", 82: "Heavy Rain Showers", 95: "Thunderstorm",
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

# Weekday Deity matched to asset_path + concise 2-sentence verse in all 6 languages
DAY_DEITIES = {
    0: {
        "asset_path": "assets/deities/mon_shiva.png",
        "title": {
            "en": "Monday — Lord Shiva",
            "ta": "திங்கள் — சிவபெருமான்",
            "hi": "सोमवार — भगवान शिव",
            "te": "సోమవారం — పరమశివుడు",
            "kn": "ಸೋಮವಾರ — ಪರಮೇಶ್ವರ",
            "ml": "തിങ്കൾ — പരമശിവൻ",
        },
        "deity_verse": {
            "en": "Om Namah Shivaya, salutations to the serene Lord who stills the restless mind. May His grace shield your home and guide every step in peace.",
            "ta": "ஓம் நம சிவாய — அமைதியின் வடிவான சிவபெருமானை வணங்குகிறோம். அவரின் திருவருள் உங்கள் இல்லத்தைக் காத்து மன அமைதியைத் தரட்டும்.",
            "hi": "ॐ नमः शिवाय — शांत स्वरूप भगवान शिव को प्रणाम। उनकी कृपा आपके परिवार की रक्षा करे और हर कदम पर शांति दे।",
            "te": "ఓం నమః శివాయ — ప్రశాంత స్వరూపుడైన పరమశివునికి వందనం. ఆయన కృప మీ ఇంటిని కాపాడి మనశ్శాంతిని ప్రసాదించుగాక.",
            "kn": "ಓಂ ನಮಃ ಶಿವಾಯ — ಶಾಂತ ಸ್ವರೂಪ ಪರಮೇಶ್ವರನಿಗೆ ನಮನಗಳು. ಅವರ ಕೃಪೆ ನಿಮ್ಮ ಕುಟುಂಬವನ್ನು ರಕ್ಷಿಸಿ ನೆಮ್ಮದಿ ನೀಡಲಿ.",
            "ml": "ഓം നമഃ ശിവായ — ശാന്തസ്വരൂപനായ പരമശിവന് പ്രണാമം. അവിടുത്തെ കൃപ നിങ്ങളുടെ കുടുംബത്തെ കാത്ത് സമാധാനം നൽകട്ടെ.",
        },
    },
    1: {
        "asset_path": "assets/deities/tue_murugan.png",
        "title": {
            "en": "Tuesday — Lord Murugan & Hanuman",
            "ta": "செவ்வாய் — முருகப்பெருமான் & அனுமன்",
            "hi": "मंगलवार — भगवान मुरुगन व हनुमान",
            "te": "మంగళవారం — సుబ్రహ్మణ్య స్వామి & హనుమాన్",
            "kn": "ಮಂಗಳವಾರ — ಸುಬ್ರಹ್ಮಣ್ಯ & ಹನುಮಾನ್",
            "ml": "ചൊവ്വ — സുബ്രഹ്മണ്യ സ്വാമി & ഹനുമാൻ",
        },
        "deity_verse": {
            "en": "Om Saravanabhavaya Namah, we invoke divine courage and steadfast devotion. May every obstacle yield to clarity, strength, and righteous action.",
            "ta": "ஓம் சரவணபவாய நம — வீரமும் ஞானமும் அருளும் கந்தனை வணங்குகிறோம். தடைகள் யாவும் நீங்கி இன்றைய செயல்கள் வெற்றியுடன் நிறைவேறட்டும்.",
            "hi": "ॐ शरवणभवाय नमः — साहस और भक्ति के दाता को नमन। आपके मार्ग की हर बाधा दूर हो और कार्यों में सफलता मिले।",
            "te": "ఓం శరవణభవాయ నమః — ధైర్యం, భక్తి ప్రసాదించే స్వామికి వందనం. అడ్డంకులన్నీ తొలగి మీ పనులు విజయవంతంగా సాగుగాక.",
            "kn": "ಓಂ ಶರವಣಭವಾಯ ನಮಃ — ಧೈರ್ಯ ಮತ್ತು ಭಕ್ತಿ ನೀಡುವ ಸ್ವಾಮಿಗೆ ನಮನ. ಎಲ್ಲಾ ಅಡೆತಡೆಗಳು ನಿವಾರಣೆಯಾಗಿ ಕಾರ್ಯಗಳಲ್ಲಿ ಜಯ ಸಿಗಲಿ.",
            "ml": "ഓം ശരവണഭവായ നമഃ — ധൈര്യവും ഭക്തിയും നൽകുന്ന സ്വാമിക്ക് പ്രണാമം. തടസ്സങ്ങളെല്ലാം നീങ്ങി കർമ്മങ്ങളിൽ വിജയം ഉണ്ടാകട്ടെ.",
        },
    },
    2: {
        "asset_path": "assets/deities/wed_vinayagar.png",
        "title": {
            "en": "Wednesday — Lord Vinayagar & Perumal",
            "ta": "புதன் — விநாயகர் & பெருமாள்",
            "hi": "बुधवार — भगवान गणेश व विष्णु",
            "te": "బుధవారం — వినాయకుడు & శ్రీమన్నారాయణుడు",
            "kn": "ಬುಧವಾರ — ವಿನಾಯಕ & ಶ್ರೀಮನ್ನಾರಾಯಣ",
            "ml": "ബുധൻ — ഗണപതി & മഹാവിഷ്ണു",
        },
        "deity_verse": {
            "en": "Om Gam Ganapataye Namah, remover of obstacles and lord of wisdom. May discernment and steady grace bless every undertaking today.",
            "ta": "ஓம் கம் கணபதயே நம — விக்னங்களைத் தீர்க்கும் விநாயகரை வணங்குகிறோம். நல்லறிவும் திருவருளும் துணைநின்று இன்றைய நாள் இனிதாக அமையட்டும்.",
            "hi": "ॐ गं गणपतये नमः — विघ्नहर्ता और बुद्धि के स्वामी को प्रणाम। विवेक और शुभ कृपा से आपके सभी कार्य मंगलमय हों।",
            "te": "ఓం గం గణపతయే నమః — విఘ్నాలను తొలగించే గణనాథునికి వందనం. సద్బుద్ధి, శుభ కృపతో నేటి పనులు చక్కగా సాగుగాక.",
            "kn": "ಓಂ ಗಂ ಗಣಪತಯೇ ನಮಃ — ವಿಘ್ನ ನಿವಾರಕ ಗಣಪತಿಗೆ ನಮನಗಳು. ಸದ್ಬುದ್ಧಿ ಮತ್ತು ಶುಭ ಕೃಪೆಯಿಂದ ಇಂದಿನ ಕಾರ್ಯಗಳು ಸಫಲವಾಗಲಿ.",
            "ml": "ഓം ഗം ഗണപതയേ നമഃ — വിഘ്നങ്ങൾ അകറ്റുന്ന ഗണപതിക്ക് പ്രണാമം. സദ്ബുദ്ധിയും അനുഗ്രഹവും കൊണ്ട് ഇന്നത്തെ കർമ്മങ്ങൾ ശുഭമാകട്ടെ.",
        },
    },
    3: {
        "asset_path": "assets/deities/thu_guru.png",
        "title": {
            "en": "Thursday — Sri Dakshinamoorthy & Guru",
            "ta": "வியாழன் — ஸ்ரீ தட்சிணாமூர்த்தி & குரு",
            "hi": "गुरुवार — श्री दक्षिणामूर्ति व गुरु",
            "te": "గురువారం — శ్రీ దక్షిణామూర్తి & గురువు",
            "kn": "ಗುರುವಾರ — ಶ್ರೀ ದಕ್ಷಿಣಾಮೂರ್ತಿ & ಗುರು",
            "ml": "വ്യാഴം — ശ്രീ ദക്ഷിണാമൂർത്തി & ഗുരു",
        },
        "deity_verse": {
            "en": "Om Gurave Namah, salutations to the silent teacher who dispels ignorance. May wisdom, patience, and sound judgment guide your day.",
            "ta": "ஓம் குரவே நம — அறியாமை இருளை அகற்றும் குருபகவானை வணங்குகிறோம். தெளிவான ஞானமும் பொறுமையும் உங்கள் முடிவுகளை வழிநடத்தட்டும்.",
            "hi": "ॐ गुरवे नमः — अज्ञान के अंधकार को मिटाने वाले गुरु को प्रणाम। ज्ञान, धैर्य और विवेक आपके निर्णयों का मार्गदर्शन करें।",
            "te": "ఓం గురవే నమః — అజ్ఞానాన్ని తొలగించే సద్గురువుకు వందనం. జ్ఞానం, సహనం, మంచి విచక్షణ మీ నిర్ణయాలకు తోడుగా ఉండుగాక.",
            "kn": "ಓಂ ಗುರವೇ ನಮಃ — ಅಜ್ಞಾನವನ್ನು ಕಳೆಯುವ ಗುರುವಿಗೆ ನಮನಗಳು. ಜ್ಞಾನ, ತಾಳ್ಮೆ ಮತ್ತು ಸದ್ವಿಚಾರ ನಿಮ್ಮ ನಿರ್ಧಾರಗಳನ್ನು ಮುನ್ನಡೆಸಲಿ.",
            "ml": "ഓം ഗുരവേ നമഃ — അജ്ഞാനം അകറ്റുന്ന ഗുരുവിന് പ്രണാമം. ജ്ഞാനവും ക്ഷമയും വിവേകവും നിങ്ങളുടെ തീരുമാനങ്ങൾക്ക് വഴികാട്ടട്ടെ.",
        },
    },
    4: {
        "asset_path": "assets/deities/fri_amman.png",
        "title": {
            "en": "Friday — Goddess Mahalakshmi & Amman",
            "ta": "வெள்ளி — மகாலட்சுமி & அம்மன்",
            "hi": "शुक्रवार — देवी महालक्ष्मी व अम्मान",
            "te": "శుక్రవారం — మహాలక్ష్మీ దేవి & అమ్మవారు",
            "kn": "ಶುಕ್ರವಾರ — ಮಹಾಲಕ್ಷ್ಮಿ & ಅಮ್ಮನವರು",
            "ml": "വെള്ളി — മഹാലക്ഷ്മി & ദേവി",
        },
        "deity_verse": {
            "en": "Om Shreem Mahalakshmyai Namah, we bow to the Divine Mother of grace and harmony. May prosperity, kindness, and auspiciousness fill your home.",
            "ta": "ஓம் ஸ்ரீம் மகாலட்சுமியை நம — மங்களமும் ஐஸ்வர்யமும் அருளும் அன்னையை வணங்குகிறோம். உங்கள் இல்லத்தில் அமைதியும் வளமும் நிறைந்திருக்கட்டும்.",
            "hi": "ॐ श्रीं महालक्ष्म्यै नमः — करुणा और सौभाग्य की देवी को नमन। आपके घर में सुख, शांति और समृद्धि का वास हो।",
            "te": "ఓం శ్రీం మహాలక్ష్మ్యై నమః — శుభం, ఐశ్వర్యం ప్రసాదించే జగన్మాతకు వందనం. మీ ఇంట సుఖశాంతులు, సంపదలు వెల్లివిరియుగాక.",
            "kn": "ಓಂ ಶ್ರೀಂ ಮಹಾಲಕ್ಷ್ಮ್ಯೈ ನಮಃ — ಮಂಗಳ ಮತ್ತು ಸೌಭಾಗ್ಯ ನೀಡುವ ತಾಯಿಗೆ ನಮನ. ನಿಮ್ಮ ಮನೆಯಲ್ಲಿ ಶಾಂತಿ, ನೆಮ್ಮದಿ ಮತ್ತು ಸಮೃದ್ಧಿ ನೆಲೆಸಲಿ.",
            "ml": "ഓം ശ്രീം മഹാലക്ഷ്മ്യൈ നമഃ — ഐശ്വര്യവും മംഗളവും നൽകുന്ന ദേവിക്ക് പ്രണാമം. നിങ്ങളുടെ ഭവനത്തിൽ സമാധാനവും സമൃദ്ധിയും നിറയട്ടെ.",
        },
    },
    5: {
        "asset_path": "assets/deities/sat_thirumal.png",
        "title": {
            "en": "Saturday — Lord Thirumal (Venkateswara)",
            "ta": "சனி — திருவேங்கடமுடையான் (பெருமாள்)",
            "hi": "शनिवार — भगवान वेंकटेश्वर (तिरुमल)",
            "te": "శనివారం — శ్రీ వేంకటేశ్వర స్వామి",
            "kn": "ಶನಿವಾರ — ಶ್ರೀ ವೆಂಕಟೇಶ್ವರ ಸ್ವಾಮಿ",
            "ml": "ശനി — ശ്രീ വെങ്കിടേശ്വര സ്വാമി",
        },
        "deity_verse": {
            "en": "Om Namo Venkatesaya, refuge of devotees and sustainer of dharma. May His protection steady your spirit and bring enduring peace.",
            "ta": "ஓம் நமோ வேங்கடேசாய — பக்தர்களைக் காக்கும் திருவேங்கடவனை வணங்குகிறோம். அவரின் திருவருள் மன உறுதியையும் நிலையான அமைதியையும் தரட்டும்.",
            "hi": "ॐ नमो वेंकटेशाय — भक्तों के रक्षक और धर्म के पालक को प्रणाम। उनकी कृपा आपके मन को स्थिरता और अटूट शांति प्रदान करे।",
            "te": "ఓం నమో వేంకటేశాయ — భక్తులను రక్షించే శ్రీనివాసునికి వందనం. ఆయన అభయం మీ మనసుకు స్థిరత్వం, శాంతిని ప్రసాదించుగాక.",
            "kn": "ಓಂ ನಮೋ ವೆಂಕಟೇಶಾಯ — ಭಕ್ತರ ರಕ್ಷಕ ಶ್ರೀನಿವಾಸನಿಗೆ ನಮನಗಳು. ಅವರ ಕೃಪೆ ನಿಮ್ಮ ಮನಸ್ಸಿಗೆ ಸ್ಥಿರತೆ ಮತ್ತು ಶಾಂತಿಯನ್ನು ನೀಡಲಿ.",
            "ml": "ഓം നമോ വെങ്കടേശായ — ഭക്തരെ രക്ഷിക്കുന്ന ശ്രീനിവാസന് പ്രണാമം. അവിടുത്തെ കൃപ മനസ്സിന് സ്ഥിരതയും ശാന്തിയും നൽകട്ടെ.",
        },
    },
    6: {
        "asset_path": "assets/deities/sun_surya.png",
        "title": {
            "en": "Sunday — Lord Surya Narayana",
            "ta": "ஞாயிறு — சூரிய நாராயணர்",
            "hi": "रविवार — भगवान सूर्य नारायण",
            "te": "ఆదివారం — సూర్య నారాయణ స్వామి",
            "kn": "ಭಾನುವಾರ — ಸೂರ್ಯ ನಾರಾಯಣ ಸ್ವಾಮಿ",
            "ml": "ഞായർ — സൂര്യനാരായണ സ്വാമി",
        },
        "deity_verse": {
            "en": "Om Suryaya Namah, radiant giver of light, health, and vitality. May your day shine with clarity, energy, and purposeful grace.",
            "ta": "ஓம் சூர்யாய நம — ஆரோக்கியமும் ஒளியும் அருளும் சூரிய பகவானை வணங்குகிறோம். தெளிவான சிந்தனையும் நலமும் இன்று உங்களுக்குத் துணைநிற்கட்டும்.",
            "hi": "ॐ सूर्याय नमः — प्रकाश, आरोग्य और ऊर्जा के दाता को प्रणाम। आपका दिन स्पष्टता, उत्तम स्वास्थ्य और शुभ ऊर्जा से आलोकित हो।",
            "te": "ఓం సూర్యాయ నమః — ఆరోగ్యం, తేజస్సు ప్రసాదించే సూర్యదేవునికి వందనం. మీ రోజు స్పష్టత, ఉత్సాహం, శుభ శక్తితో ప్రకాశించుగాక.",
            "kn": "ಓಂ ಸೂರ್ಯಾಯ ನಮಃ — ಬೆಳಕು, ಆರೋಗ್ಯ ಮತ್ತು ಚೈತನ್ಯ ನೀಡುವ ಸೂರ್ಯದೇವನಿಗೆ ನಮನ. ನಿಮ್ಮ ದಿನ ಸ್ಪಷ್ಟತೆ ಮತ್ತು ಶುಭ ಶಕ್ತಿಯಿಂದ ಬೆಳಗಲಿ.",
            "ml": "ഓം സൂര്യായ നമഃ — പ്രകാശവും ആരോഗ്യവും നൽകുന്ന സൂര്യദേവന് പ്രണാമം. വ്യക്തതയും ഉന്മേഷവും ശുഭോർജ്ജവും ഇന്ന് നിങ്ങളോടൊപ്പം ഉണ്ടാകട്ടെ.",
        },
    },
}

# One Scripture per day (Bhagavad Gita OR Upanishads OR Vedas — never all 3 in one card)
SCRIPTURE_ROTATION = [
    {
        "source": "Bhagavad Gita (2.47)",
        "verse": "Karmanye vadhikaraste ma phaleshu kadachana",
        "meaning": {
            "en": "Focus wholeheartedly on your duty today, without anxiety over results.",
            "ta": "பலனைப் பற்றிய கவலையின்றி இன்றைய கடமையை முழு மனதுடன் செய்யுங்கள்.",
            "hi": "फल की चिंता किए बिना आज अपने कर्तव्य का पूरी निष्ठा से पालन करें।",
            "te": "ఫలితం గురించి ఆందోళన లేకుండా నేటి మీ కర్తవ్యాన్ని నిష్ఠతో నిర్వర్తించండి.",
            "kn": "ಫಲದ ಚಿಂತೆಯಿಲ್ಲದೆ ಇಂದಿನ ನಿಮ್ಮ ಕರ್ತವ್ಯವನ್ನು ಶ್ರದ್ಧೆಯಿಂದ ನಿರ್ವಹಿಸಿ.",
            "ml": "ഫലത്തെക്കുറിച്ച് ഉത്കണ്ഠപ്പെടാതെ ഇന്നത്തെ കർത്തവ്യം ആത്മാർത്ഥമായി ചെയ്യുക.",
        },
    },
    {
        "source": "Katha Upanishad (1.3.14)",
        "verse": "Uttishthata jagrata prapya varan nibodhata",
        "meaning": {
            "en": "Arise, awake, and walk steadily toward higher wisdom and clarity.",
            "ta": "எழுந்திருங்கள், விழித்திருங்கள்; உயர்ந்த ஞானத்தை நோக்கி உறுதியுடன் நடங்கள்.",
            "hi": "उठो, जागो और श्रेष्ठ ज्ञान एवं स्पष्टता की ओर दृढ़ता से बढ़ो।",
            "te": "మేల్కొనండి, చైతన్యవంతులై ఉన్నత జ్ఞానం వైపు దృఢంగా అడుగువేయండి.",
            "kn": "ಏಳಿ, ಎಚ್ಚರಗೊಳ್ಳಿ; ಉನ್ನತ ಜ್ಞಾನದತ್ತ ದೃಢವಾಗಿ ಮುನ್ನಡೆಯಿರಿ.",
            "ml": "ഉണരുക, ജാഗ്രതയോടെ ഉന്നത ജ്ഞാനത്തിലേക്ക് ഉറപ്പോടെ മുന്നേറുക.",
        },
    },
    {
        "source": "Rigveda (10.191.2)",
        "verse": "Sam gachadhvam sam vadadhvam sam vo manansi janatam",
        "meaning": {
            "en": "Move together in harmony, speak with kindness, and let minds unite in peace.",
            "ta": "ஒற்றுமையுடன் நடப்போம், அன்புடன் பேசுவோம், அமைதியில் மனம் இணைவோம்.",
            "hi": "सद्भाव के साथ मिलकर चलें, मधुर बोलें और मन में शांति बनाए रखें।",
            "te": "సామరస్యంతో కలిసి నడవండి, ప్రేమతో మాట్లాడండి, శాంతితో మనసులు కలవనివ్వండి.",
            "kn": "ಸಾಮರಸ್ಯದಿಂದ ಜೊತೆಯಾಗಿ ನಡೆಯಿರಿ, ಪ್ರೀತಿಯಿಂದ ಮಾತನಾಡಿ, ಮನಸ್ಸುಗಳು ಶಾಂತಿಯಲ್ಲಿ ಒಂದಾಗಲಿ.",
            "ml": "ഐക്യത്തോടെ ഒരുമിച്ച് നടക്കുക, സ്നേഹത്തോടെ സംസാരിക്കുക, മനസ്സുകൾ ശാന്തിയിൽ ഒന്നാകട്ടെ.",
        },
    },
    {
        "source": "Bhagavad Gita (2.48)",
        "verse": "Samatvam yoga uchyate",
        "meaning": {
            "en": "Calm balance of mind in both ease and challenge is true spiritual strength.",
            "ta": "இன்பத்திலும் சவாலிலும் மன சமநிலை காப்பதே உண்மையான யோகம்.",
            "hi": "सुख और चुनौती दोनों में मन का संतुलन बनाए रखना ही सच्चा योग है।",
            "te": "సుఖదుఃఖాలలో మనసు సమతుల్యతను నిలుపుకోవడమే నిజమైన యోగం.",
            "kn": "ಸುಖ ಮತ್ತು ಸವಾಲು ಎರಡರಲ್ಲೂ ಮನಸ್ಸಿನ ಸಮತೋಲನ ಕಾಯ್ದುಕೊಳ್ಳುವುದೇ ನಿಜವಾದ ಯೋಗ.",
            "ml": "സുഖത്തിലും വെല്ലുവിളിയിലും മനസ്സിന്റെ സമനില പാലിക്കുന്നതാണ് യഥാർത്ഥ യോഗം.",
        },
    },
    {
        "source": "Isha Upanishad (1)",
        "verse": "Isavasyam idam sarvam yat kincha jagatyam jagat",
        "meaning": {
            "en": "All that exists in this universe is pervaded by the Divine; live with gratitude.",
            "ta": "இவ்வுலகில் உள்ள அனைத்தும் இறைவனால் நிறைந்துள்ளது; நன்றியுணர்வுடன் வாழுங்கள்.",
            "hi": "इस जगत का कण-कण ईश्वर से व्याप्त है; कृतज्ञता के साथ जीवन जिएं।",
            "te": "ఈ సృష్టిలోని ప్రతి అణువు దైవంతో నిండి ఉంది; కృతజ్ఞతతో జీవించండి.",
            "kn": "ಈ ಜಗತ್ತಿನ ಪ್ರತಿಯೊಂದು ಕಣವೂ ದೈವದಿಂದ ಆವೃತವಾಗಿದೆ; ಕೃತಜ್ಞತೆಯಿಂದ ಬಾಳಿ.",
            "ml": "ഈ പ്രപഞ്ചത്തിലെല്ലാം ഈശ്വരനാൽ നിറഞ്ഞിരിക്കുന്നു; കൃതജ്ഞതയോടെ ജീവിക്കുക.",
        },
    },
    {
        "source": "Rigveda (1.89.1)",
        "verse": "A no bhadrah kratavo yantu vishwatah",
        "meaning": {
            "en": "Let noble, auspicious, and uplifting thoughts come to us from every direction.",
            "ta": "நல்ல, மங்களகரமான எண்ணங்கள் எல்லாத் திசைகளிலிருந்தும் நம்மை வந்தடையட்டும்.",
            "hi": "श्रेष्ठ और शुभ विचार चारों दिशाओं से हमारे पास आएं।",
            "te": "మంచి, శుభకరమైన ఆలోచనలు అన్ని దిశల నుండి మనకు చేరుగాక.",
            "kn": "ಶ್ರೇಷ್ಠ ಮತ್ತು ಮಂಗಳಕರ ಆಲೋಚನೆಗಳು ಎಲ್ಲಾ ದಿಕ್ಕುಗಳಿಂದಲೂ ನಮಗೆ ಬರಲಿ.",
            "ml": "ശ്രേഷ്ഠവും മംഗളകരവുമായ ചിന്തകൾ എല്ലാ ദിക്കുകളിൽ നിന്നും നമ്മിലേക്ക് വരട്ടെ.",
        },
    },
]

WOW_BY_LANG = {
    "en": "Steady Focus • Helpful Partnership • Timely Resolution",
    "ta": "நிலையான கவனம் • நல்ல ஒத்துழைப்பு • சரியான நேரத்தில் தீர்வு",
    "hi": "स्थिर एकाग्रता • सहायक साझेदारी • समय पर समाधान",
    "te": "స్థిరమైన ఏకాగ్రత • మంచి సహకారం • సమయానికి పరిష్కారం",
    "kn": "ಸ್ಥಿರ ಏಕಾಗ್ರತೆ • ಉತ್ತಮ ಸಹಕಾರ • ಸಕಾಲಿಕ ಪರಿಹಾರ",
    "ml": "സ്ഥിരമായ ശ്രദ്ധ • നല്ല സഹകരണം • സമയബന്ധിതമായ പരിഹാരം",
}

TROY_OUNCE_TO_GRAM = 31.1034768
INDIA_BULLION_PREMIUM_FACTOR = 1.065


def normalize_location_key(raw_loc: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]+", "_", raw_loc.upper()).strip("_")
    return cleaned or "CHENNAI"


def parse_area_and_city(raw_loc: str) -> tuple[str, str]:
    parts = [re.sub(r"\s+", " ", p).strip() for p in raw_loc.split(",", 1)]
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0].title(), parts[1].title()
    city = parts[0].title() if parts and parts[0] else "Chennai"
    return "", city


async def resolve_location_coords(session: aiohttp.ClientSession, raw_loc: str) -> dict | None:
    area, city = parse_area_and_city(raw_loc)
    city_key = city.upper()
    fallback = CITY_COORDS.get(city_key)

    if area:
        query = f"{area} {city}"
        url = f"https://geocoding-api.open-meteo.com/v1/search?name={aiohttp.helpers.quote(query)}&count=3&language=en&format=json"
        try:
            async with session.get(url, timeout=12) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results") or []
                    for r in results:
                        admin_blob = " ".join(str(r.get(k, "")) for k in ("name", "admin1", "admin2", "admin3", "country")).lower()
                        if city.lower() in admin_blob or "india" in admin_blob:
                            return {
                                "name": f"{area}, {city}",
                                "lat": float(r["latitude"]),
                                "lon": float(r["longitude"]),
                            }
                    if results:
                        return {
                            "name": f"{area}, {city}",
                            "lat": float(results[0]["latitude"]),
                            "lon": float(results[0]["longitude"]),
                        }
        except Exception:
            pass

    if fallback:
        return {"name": f"{area}, {city}" if area else fallback["name"], "lat": fallback["lat"], "lon": fallback["lon"]}
    return None


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
            "rate_22k": f"₹{rate_22k:,}/g",
            "rate_24k": f"₹{rate_24k:,}/g",
            "rate_18k": f"₹{rate_18k:,}/g",
            "rate_silver": f"₹{silver_1g}/g",
            "gold_summary": f"22K: ₹{rate_22k:,}/g | 24K: ₹{rate_24k:,}/g",
        }
    return {
        "rate_22k": "Check showroom",
        "rate_24k": "Check showroom",
        "rate_18k": "Check showroom",
        "rate_silver": "Check showroom",
        "gold_summary": "Check showroom",
    }


async def fetch_city_weather(session: aiohttp.ClientSession, lat: float, lon: float) -> dict:
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,weather_code"
        "&daily=precipitation_probability_max&forecast_days=1&timezone=Asia%2FKolkata"
    )
    try:
        async with session.get(url, timeout=12) as resp:
            if resp.status == 200:
                payload = await resp.json()
                cur = payload["current"]
                w_code = int(cur["weather_code"])
                cond = WEATHER_CODES.get(w_code, "Pleasant")
                weather_str = f"{round(cur['temperature_2m'])}°C, {cond}, Humidity {round(cur['relative_humidity_2m'])}%"
                probs = payload.get("daily", {}).get("precipitation_probability_max") or []
                rain_prob = int(probs[0]) if probs and probs[0] is not None else 0

                if w_code in {65, 82, 95}:
                    severity = "CAUTION_HEAVY_RAIN"
                elif w_code in {71, 73, 75}:
                    severity = "CAUTION_SNOW"
                elif w_code in {45, 48}:
                    severity = "CAUTION_FOG"
                elif rain_prob >= 40 or w_code in {51, 53, 61, 63, 80}:
                    severity = "UMBRELLA"
                else:
                    severity = "NORMAL"

                return {
                    "weather": weather_str,
                    "rain_chance_pct": rain_prob,
                    "condition_severity": severity,
                }
    except Exception:
        pass
    return {"weather": "29°C, Partly Cloudy", "rain_chance_pct": 20, "condition_severity": "NORMAL"}


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
    deity_spec = DAY_DEITIES[weekday]
    scripture_spec = SCRIPTURE_ROTATION[(day_of_year - 1) % len(SCRIPTURE_ROTATION)]

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    try:
        db_locs = await pool.fetch(
            "SELECT DISTINCT TRIM(city) AS c FROM subscribers WHERE is_active = TRUE AND city IS NOT NULL AND TRIM(city) <> '';"
        )
        raw_locations = list(CITY_COORDS.keys()) + [r["c"] for r in db_locs]

        key_to_raw: dict[str, str] = {}
        for loc in raw_locations:
            k = normalize_location_key(loc)
            if k not in key_to_raw:
                key_to_raw[k] = loc

        async with aiohttp.ClientSession() as session:
            calendar_notes = await fetch_sheet_tab_csv(session, "Calendar_Notes")

            occasion_by_lang: dict[str, dict] = {
                lang: {"occasion_title": "", "occasion_temple": "", "asset_path": deity_spec["asset_path"]}
                for lang in SUPPORTED_LANGS
            }
            for note in calendar_notes:
                if str(note.get("event_date", "")).strip() == edition_date:
                    n_lang = str(note.get("language", "en")).strip().lower() or "en"
                    if n_lang in occasion_by_lang:
                        ev_name = str(note.get("event_name", "")).strip()
                        temple_hl = str(note.get("temple_highlight", "")).strip()
                        special_sl = str(note.get("special_slogan", "")).strip()
                        combined = " — ".join(p for p in [temple_hl, special_sl] if p)
                        occasion_by_lang[n_lang] = {
                            "occasion_title": ev_name,
                            "occasion_temple": combined,
                            "asset_path": str(note.get("asset_path", "")).strip() or deity_spec["asset_path"],
                        }

            gold_data = await fetch_bullion_rates(session)

            city_payloads: dict[str, dict] = {}
            for loc_key, raw_loc in key_to_raw.items():
                coords = await resolve_location_coords(session, raw_loc)
                if not coords:
                    continue
                weather_info, ausp_str = await asyncio.gather(
                    fetch_city_weather(session, coords["lat"], coords["lon"]),
                    fetch_auspicious_window(session, coords["lat"], coords["lon"], edition_date, weekday),
                )
                city_payloads[loc_key] = {
                    "label": coords["name"],
                    **weather_info,
                    "auspicious_time": ausp_str,
                }

        buckets = []
        for lang in SUPPORTED_LANGS:
            deity_payload = {
                "title": deity_spec["title"][lang],
                "deity_verse": deity_spec["deity_verse"][lang],
                "asset_path": deity_spec["asset_path"],
            }
            scripture_payload = {
                "source": scripture_spec["source"],
                "verse": scripture_spec["verse"],
                "meaning": scripture_spec["meaning"][lang],
            }
            buckets.append((lang, "DEITY_DAY_OF_WEEK", deity_payload, None))
            buckets.append((lang, "DEITY_ALL_OCCASIONS", occasion_by_lang[lang], None))
            buckets.append((lang, "SCRIPTURE_DAILY", scripture_payload, None))
            buckets.append((lang, "GOLD_INR", gold_data, None))
            for r in ["Mesham", "Rishabam", "Mithunam", "Kadagam", "Simmam", "Kanni", "Thulam", "Vrischikam", "Dhanusu", "Magaram", "Kumbam", "Meenam"]:
                buckets.append((lang, f"RASI_{r.upper()}", {"three_words": WOW_BY_LANG[lang]}, None))

        for loc_key, loc_data in city_payloads.items():
            buckets.append(("en", f"CITY_{loc_key}", loc_data, None))

        for lang, bucket_key, payload, file_id in buckets:
            await pool.execute(
                """
                INSERT INTO daily_shared_cache (edition_date, language, bucket_key, payload_json, telegram_file_id)
                VALUES ($1::date, $2, $3, $4::jsonb, $5)
                ON CONFLICT (edition_date, language, bucket_key) DO UPDATE SET
                    payload_json = EXCLUDED.payload_json,
                    telegram_file_id = COALESCE(EXCLUDED.telegram_file_id, daily_shared_cache.telegram_file_id);
                """,
                edition_date, lang, bucket_key, json.dumps(payload), file_id,
            )
        print(f"[{edition_date}] AURA daily_shared_cache updated ({len(buckets)} buckets).")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(build_and_store_cache())
