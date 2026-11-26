# broadcast_daily.py — AURA Daily Broadcaster with Full Regional Localization
import os
import re
import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
import aiohttp
import asyncpg

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("broadcast_daily")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
UPI_CHECKOUT_BASE_URL = os.environ.get("UPI_GATEWAY_CHECKOUT_URL", "https://example.com/upi")
IST = timezone(timedelta(hours=5, minutes=30))
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
BATCH_CONCURRENCY = 25

AURA_HEADER = "ॐ  AURA  |  Daily Morning Grace &amp; Divine Blessings  ॐ"
DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━━━━━"

SHORT_DISCLAIMER = (
    "⚖️ <i>General info only (incl. devotional, Rasi, indicative bullion &amp; weather); "
    "not financial, medical, legal, or safety advice. Verify independently.</i>"
)

CARD_LABELS = {
    "en": {
        "blessing_with": "Daily Blessing With",
        "gold_rate": "Gold Rate",
        "silver_rate": "Silver Rate",
        "auspicious": "Auspicious Timing [Plan Your Decisions]",
        "wow": "WoW [Words of Wisdom]",
        "quote": "Quote",
        "weather": "Weather [Plan Your Day]",
        "rain_suffix": " • {pct}% rain chance",
        "caution": "⚠️ <b>CAUTION:</b> Heavy rain / snow / low visibility possible—plan extra travel buffer.",
        "umbrella": "☂️ <b>Umbrella Notice:</b> Carry an umbrella or rain cover before stepping out.",
        "care_caution": "💛 <i>Care: Your safety comes first today—travel unhurriedly.</i>",
        "care_umbrella": "💛 <i>Care: May your steps stay dry, safe, and peaceful today.</i>",
        "care_normal": "💛 <i>Care: Wishing you a calm, healthy, and steady day ahead.</i>",
        "btn_profile": "👤 Profile",
        "btn_other": "📣 Other Services",
        "btn_12pillars": "🏛️ 12 Pillars View",
        "btn_pay": "🛒 Shop",
        "btn_support": "💬 Help & Feedback",
        "btn_privacy": "🔒 Privacy & Data (DPDPA)",
        "btn_delete": "🗑️ Delete My Data (DPDPA)",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "ta": {
        "blessing_with": "தினசரி ஆசீர்வாதம் — உடன்",
        "gold_rate": "Gold Rate / தங்கம் விலை",
        "silver_rate": "Silver Rate / வெள்ளி விலை",
        "auspicious": "நல்ல நேரம் [உங்கள் முடிவுகளைத் திட்டமிடுங்கள்]",
        "wow": "WoW [ஞான மொழிகள்]",
        "quote": "Quote / பொன்மொழி",
        "weather": "வானிலை [உங்கள் நாளைத் திட்டமிடுங்கள்]",
        "rain_suffix": " • {pct}% மழை வாய்ப்பு",
        "caution": "⚠️ <b>எச்சரிக்கை:</b> கனமழை / பனி / குறைந்த பார்வை வாய்ப்பு—கவனமாக பயணிக்கவும்.",
        "umbrella": "☂️ <b>குடை அறிவிப்பு:</b> வெளியே செல்லும் முன் குடை எடுத்துச் செல்லவும்.",
        "care_caution": "💛 <i>அக்கறை: உங்கள் பாதுகாப்பே முக்கியம்—அவசரமின்றி பயணிக்கவும்.</i>",
        "care_umbrella": "💛 <i>அக்கறை: இன்று உங்கள் பயணம் பாதுகாப்பாகவும் அமைதியாகவும் அமையட்டும்.</i>",
        "care_normal": "💛 <i>அக்கறை: இன்று அமைதியான, ஆரோக்கியமான நாளாக அமைய வாழ்த்துகள்.</i>",
        "btn_profile": "👤 சுயவிவரம்",
        "btn_other": "📣 மற்ற சேவைகள்",
        "btn_12pillars": "🏛️ 12 தூண்கள் பார்வை",
        "btn_pay": "🛒 Shop",
        "btn_support": "💬 உதவி &amp; கருத்து",
        "btn_privacy": "🔒 தனியுரிமை &amp; தரவு (DPDPA)",
        "btn_delete": "🗑️ என் தரவை நீக்கு (DPDPA)",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "hi": {
        "blessing_with": "दैनिक आशीर्वाद — साथ में",
        "gold_rate": "Gold Rate / सोना भाव",
        "silver_rate": "Silver Rate / चांदी भाव",
        "auspicious": "शुभ समय [अपने निर्णयों की योजना बनाएं]",
        "wow": "WoW [ज्ञान की बातें]",
        "quote": "Quote / अनमोल वचन",
        "weather": "मौसम [दिन की योजना]",
        "rain_suffix": " • {pct}% बारिश की संभावना",
        "caution": "⚠️ <b>सावधानी:</b> भारी बारिश / कोहरा संभव—यात्रा में अतिरिक्त समय रखें।",
        "umbrella": "☂️ <b>छाता सूचना:</b> बाहर निकलने से पहले छाता या रेन कवर साथ रखें।",
        "care_caution": "💛 <i>देखभाल: आपकी सुरक्षा सर्वोपरि है—संभलकर यात्रा करें।</i>",
        "care_umbrella": "💛 <i>देखभाल: आज आपके कदम सुरक्षित और शांतिपूर्ण रहें।</i>",
        "care_normal": "💛 <i>देखभाल: आपका दिन शांत, स्वस्थ और मंगलमय हो।</i>",
        "btn_profile": "👤 प्रोफ़ाइल",
        "btn_other": "📣 अन्य सेवाएं",
        "btn_12pillars": "🏛️ 12 पिलर्स दृश्य",
        "btn_pay": "🛒 Shop",
        "btn_support": "💬 सहायता व प्रतिक्रिया",
        "btn_privacy": "🔒 गोपनीयता व डेटा (DPDPA)",
        "btn_delete": "🗑️ मेरा डेटा हटाएं (DPDPA)",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "te": {
        "blessing_with": "రోజువారీ ఆశీర్వాదం — తో",
        "gold_rate": "Gold Rate / బంగారం ధర",
        "silver_rate": "Silver Rate / వెండి ధర",
        "auspicious": "శుభ సమయం [మీ నిర్ణయాలను ప్రణాళిక చేయండి]",
        "wow": "WoW [జ్ఞాన వాక్కులు]",
        "quote": "Quote / సూక్తి",
        "weather": "వాతావరణం [రోజు ప్రణాళిక]",
        "rain_suffix": " • {pct}% వర్షం అవకాశం",
        "caution": "⚠️ <b>జాగ్రత్త:</b> భారీ వర్షం / పొగమంచు అవకాశం—జాగ్రత్తగా ప్రయాణించండి.",
        "umbrella": "☂️ <b>గొడుగు సూచన:</b> బయటకు వెళ్లే ముందు గొడుగు వెంట తీసుకెళ్లండి.",
        "care_caution": "💛 <i>శ్రద్ధ: మీ భద్రతే ముఖ్యం—నిదానంగా, సురక్షితంగా ప్రయాణించండి.</i>",
        "care_umbrella": "💛 <i>శ్రద్ధ: నేటి మీ ప్రయాణం సురక్షితంగా, ప్రశాంతంగా సాగుగాక.</i>",
        "care_normal": "💛 <i>శ్రద్ధ: మీకు ప్రశాంతమైన, ఆరోగ్యకరమైన రోజు కలగాలని కోరుకుంటున్నాము.</i>",
        "btn_profile": "👤 ప్రొఫైల్",
        "btn_other": "📣 ఇతర సేవలు",
        "btn_12pillars": "🏛️ 12 పిల్లర్స్ వీక్షణ",
        "btn_pay": "🛒 Shop",
        "btn_support": "💬 సహాయం &amp; అభిప్రాయం",
        "btn_privacy": "🔒 గోప్యత &amp; డేటా (DPDPA)",
        "btn_delete": "🗑️ నా డేటా తొలగించండి (DPDPA)",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "kn": {
        "blessing_with": "ದೈನಂದಿನ ಆಶೀರ್ವಾದ — ಜೊತೆಗೆ",
        "gold_rate": "Gold Rate / ಚಿನ್ನ ದರ",
        "silver_rate": "Silver Rate / ಬೆಳ್ಳಿ ದರ",
        "auspicious": "ಶುಭ ಸಮಯ [ನಿಮ್ಮ ನಿರ್ಧಾರಗಳನ್ನು ಯೋಜಿಸಿ]",
        "wow": "WoW [ಜ್ಞಾನದ ಮಾತುಗಳು]",
        "quote": "Quote / ನುಡಿಮುತ್ತು",
        "weather": "ಹವಾಮಾನ [ದಿನದ ಯೋಜನೆ]",
        "rain_suffix": " • {pct}% ಮಳೆ ಸಾಧ್ಯತೆ",
        "caution": "⚠️ <b>ಎಚ್ಚರಿಕೆ:</b> ಭಾರೀ ಮಳೆ / ಮಂಜು ಸಾಧ್ಯತೆ—ಜಾಗರೂಕತೆಯಿಂದ ಪ್ರಯಾಣಿಸಿ.",
        "umbrella": "☂️ <b>ಛತ್ರಿ ಸೂಚನೆ:</b> ಹೊರಗೆ ಹೋಗುವ ಮುನ್ನ ಛತ್ರಿ ಜೊತೆಯಲ್ಲಿಡಿ.",
        "care_caution": "💛 <i>ಕಾಳಜಿ: ನಿಮ್ಮ ಸುರಕ್ಷತೆಯೇ ಮುಖ್ಯ—ನಿದಾನವಾಗಿ ಪ್ರಯಾಣಿಸಿ.</i>",
        "care_umbrella": "💛 <i>ಕಾಳಜಿ: ಇಂದಿನ ನಿಮ್ಮ ಹೆಜ್ಜೆಗಳು ಸುರಕ್ಷಿತ ಮತ್ತು ಶಾಂತಿಯುತವಾಗಿರಲಿ.</i>",
        "care_normal": "💛 <i>ಕಾಳಜಿ: ನಿಮಗೆ ಶಾಂತ, ಆರೋಗ್ಯಕರ ಮತ್ತು ಶುಭ ದಿನವಾಗಲಿ.</i>",
        "btn_profile": "👤 ಪ್ರೊಫೈಲ್",
        "btn_other": "📣 ಇತರೆ ಸೇವೆಗಳು",
        "btn_12pillars": "🏛️ 12 ಪಿಲ್ಲರ್ಸ್ ವೀಕ್ಷಣೆ",
        "btn_pay": "🛒 Shop",
        "btn_support": "💬 ಬೆಂಬಲ &amp; ಪ್ರತಿಕ್ರಿಯೆ",
        "btn_privacy": "🔒 ಗೌಪ್ಯತೆ ಮತ್ತು ಡೇಟಾ (DPDPA)",
        "btn_delete": "🗑️ ನನ್ನ ಡೇಟಾ ಅಳಿಸಿ (DPDPA)",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "ml": {
        "blessing_with": "ദൈനംദിന അനുഗ്രഹം — ഒപ്പം",
        "gold_rate": "Gold Rate / സ്വർണ്ണ നിരക്ക്",
        "silver_rate": "Silver Rate / വെള്ളി നിരക്ക്",
        "auspicious": "ശുഭ സമയം [തീരുമാനങ്ങൾ ആസൂത്രണം ചെയ്യുക]",
        "wow": "WoW [ജ്ഞാനവാക്കുകൾ]",
        "quote": "Quote / സന്ദേശം",
        "weather": "കാലാവസ്ഥ [ദിവസ ആസൂത്രണം]",
        "rain_suffix": " • {pct}% മഴ സാധ്യത",
        "caution": "⚠️ <b>ജാഗ്രത:</b> കനത്ത മഴ / മൂടൽമഞ്ഞ് സാധ്യത—യാത്രയിൽ ശ്രദ്ധിക്കുക.",
        "umbrella": "☂️ <b>കുട അറിയിപ്പ്:</b> പുറത്തിറങ്ങുന്നതിന് മുൻപ് കുട കരുതുക.",
        "care_caution": "💛 <i>കരുതൽ: നിങ്ങളുടെ സുരക്ഷയാണ് പ്രധാനം—ശ്രദ്ധയോടെ യാത്ര ചെയ്യുക.</i>",
        "care_umbrella": "💛 <i>കരുതൽ: ഇന്നത്തെ യാത്ര സുരക്ഷിതവും സമാധാനപരവുമാകട്ടെ.</i>",
        "care_normal": "💛 <i>കരുതൽ: ശാന്തവും ആരോഗ്യകരവുമായ ഒരു നല്ല ദിവസം ആശംസിക്കുന്നു.</i>",
        "btn_profile": "👤 പ്രൊഫൈൽ",
        "btn_other": "📣 മറ്റ് സേവനങ്ങൾ",
        "btn_12pillars": "🏛️ 12 പില്ലേഴ്സ് കാഴ്ച",
        "btn_pay": "🛒 Shop",
        "btn_support": "💬 സഹായവും പ്രതികരണവും",
        "btn_privacy": "🔒 സ്വകാര്യത &amp; ഡാറ്റ (DPDPA)",
        "btn_delete": "🗑️ എന്റെ ഡാറ്റ നീക്കം ചെയ്യുക (DPDPA)",
        "btn_translate": "🌐 Translate [ENG]",
    },
}


def lbl(lang: str) -> dict:
    return CARD_LABELS.get(lang) or CARD_LABELS["en"]


def normalize_city_key(raw_loc: str) -> str:
    city_part = raw_loc.split(",")[-1].strip().lower() if raw_loc else "chennai"
    cleaned = re.sub(r"[^a-z0-9]+", "_", city_part).strip("_")
    return cleaned or "chennai"


def parse_payload(raw_payload) -> dict:
    if isinstance(raw_payload, dict):
        return raw_payload
    if isinstance(raw_payload, str):
        try:
            parsed = json.loads(raw_payload)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def build_inline_keyboard_dict(edition_date: str, telegram_id: int, lang: str) -> dict:
    L = lbl(lang)
    upi_url = f"{UPI_CHECKOUT_BASE_URL}?uid={telegram_id}&ref={edition_date}"
    rows = [
        [
            {"text": L["btn_profile"], "callback_data": "panel:profile"},
            {"text": L["btn_other"], "callback_data": "menu:other_services"},
        ],
        [
            {"text": L["btn_pay"], "url": upi_url},
            {"text": L["btn_support"], "callback_data": "menu:help_feedback"},
        ],
    ]
    if lang != "en":
        rows.append([{"text": L["btn_translate"], "callback_data": f"translate:en:{edition_date}"}])
    return {"inline_keyboard": rows}


def render_message(
    deity_payload: dict,
    rasi_payload: dict,
    ausp_payload: dict,
    gold_payload: dict,
    weather_payload: dict,
    quote_payload: dict,
    lang: str,
    edition_date: str,
) -> str:
    L = lbl(lang)
    wow = L["wow"]
    quote = L["quote"]
    blessing_with = L["blessing_with"]
    gold_rate = L["gold_rate"]
    silver_rate = L["silver_rate"]
    auspicious = L["auspicious"]

    deity_block = deity_payload.get(lang) or deity_payload.get("en") or f"🪔 <b>{blessing_with}:</b> Om Namah Shivaya"

    raw_wow = rasi_payload.get(lang) or rasi_payload.get("en") or f"✨ <b>{wow}:</b> Stay steady and focused today."
    wow_block = raw_wow.replace("🌟 <b>Rasi Guidance:</b>", f"✨ <b>{wow}:</b>")

    raw_ausp = ausp_payload.get(lang) or ausp_payload.get("en") or f"⏰ <b>{auspicious}:</b> Morning 06:00–07:30 AM"
    ausp_block = raw_ausp.replace("⏳ <b>Auspicious Timing", "⏰ <b>Auspicious Timing")

    gold_block = gold_payload.get(lang) or gold_payload.get("en") or f"🟡 <b>{gold_rate} ⚪️ {silver_rate} [As of {edition_date}]</b>"
    weather_block = weather_payload.get(lang) or weather_payload.get("en") or f"🌦 <b>{L['weather']}:</b> Pleasant morning breeze"

    raw_quote = quote_payload.get(lang) or quote_payload.get("en") or f"🌟 <b>{quote}:</b> Stay calm and mindful today."
    quote_block = raw_quote.replace(f"✨ <b>{wow}:</b>", f"🌟 <b>{quote}:</b>").replace(
        "✨ <b>WoW [Words of Wisdom]:</b>", f"🌟 <b>{quote}:</b>"
    )

    body = (
        f"<b>{AURA_HEADER}</b>\n"
        f"{DIVIDER}\n\n"
        f"{deity_block}\n\n"
        f"{wow_block}\n\n"
        f"{ausp_block}\n\n"
        f"{gold_block}\n\n"
        f"{weather_block}\n\n"
        f"{quote_block}"
    )

    max_len = 4096 - len(SHORT_DISCLAIMER) - 4
    if len(body) > max_len:
        body = body[: max_len - 3].rsplit(" ", 1)[0] + "..."
    return f"{body}\n\n{SHORT_DISCLAIMER}"


async def send_to_subscriber(
    session: aiohttp.ClientSession,
    pool: asyncpg.Pool,
    sub: asyncpg.Record,
    cache_map: dict,
    edition_date: str,
) -> bool:
    uid = sub["telegram_id"]
    lang = (sub["preferred_language"] or "en").lower()
    raw_loc = (sub["locality"] or sub["city"] or "Chennai").strip()
    city_key = normalize_city_key(raw_loc)
    rasi_key = (sub["rasi"] or "mesham").strip().lower()

    deity_payload = cache_map.get(("DEITY_DAY", "TODAY"), {})
    rasi_payload = cache_map.get(("RASI", rasi_key), {})
    ausp_payload = cache_map.get(("AUSPICIOUS", city_key)) or cache_map.get(("AUSPICIOUS", "chennai"), {})
    gold_payload = cache_map.get(("GOLD_INR", "INDIA"), {})
    weather_payload = cache_map.get(("WEATHER", city_key)) or cache_map.get(("WEATHER", "chennai"), {})
    quote_payload = cache_map.get(("QUOTE", "TODAY"), {})

    text = render_message(
        deity_payload=deity_payload,
        rasi_payload=rasi_payload,
        ausp_payload=ausp_payload,
        gold_payload=gold_payload,
        weather_payload=weather_payload,
        quote_payload=quote_payload,
        lang=lang,
        edition_date=edition_date,
    )
    reply_markup = build_inline_keyboard_dict(edition_date, uid, lang)

    try:
        async with session.post(
            f"{TELEGRAM_API_BASE}/sendMessage",
            json={
                "chat_id": uid,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
            },
            timeout=15,
        ) as resp:
            if resp.status == 200:
                return True
            if resp.status == 403:
                await pool.execute(
                    "UPDATE subscribers SET is_active = FALSE, updated_at = NOW() WHERE telegram_id = $1;",
                    uid,
                )
            elif resp.status == 429:
                body = await resp.json()
                await asyncio.sleep(int(body.get("parameters", {}).get("retry_after", 3)))
            else:
                err_txt = await resp.text()
                logger.warning("Telegram sendMessage failed for uid=%s (status=%s): %s", uid, resp.status, err_txt)
    except Exception as exc:
        logger.warning("Broadcast error for uid=%s: %s", uid, exc)
    return False


async def run_broadcast() -> None:
    now_ist = datetime.now(IST)
    today_ist = now_ist.date()
    edition_date = today_ist.strftime("%Y-%m-%d")

    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    try:
        rows = await pool.fetch(
            "SELECT bucket_type, bucket_key, payload FROM daily_shared_cache WHERE edition_date = $1;",
            today_ist,
        )
        cache_map = {
            (r["bucket_type"], r["bucket_key"]): parse_payload(r["payload"])
            for r in rows
        }

        subs = await pool.fetch(
            "SELECT telegram_id, preferred_language, locality, city, rasi FROM subscribers WHERE is_active = TRUE;"
        )
        sent = 0
        async with aiohttp.ClientSession() as session:
            for i in range(0, len(subs), BATCH_CONCURRENCY):
                batch = subs[i : i + BATCH_CONCURRENCY]
                results = await asyncio.gather(
                    *(send_to_subscriber(session, pool, s, cache_map, edition_date) for s in batch)
                )
                sent += sum(1 for ok in results if ok)
                await asyncio.sleep(1.05)

        logger.info("[%s] AURA Broadcast complete: %d/%d delivered.", edition_date, sent, len(subs))
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run_broadcast())
