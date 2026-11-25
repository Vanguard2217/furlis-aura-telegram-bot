# broadcast_daily.py — AURA Daily Broadcaster with Full Regional Localization & Auto File-ID Caching
import os
import re
import html
import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta
import aiohttp
import asyncpg

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
UPI_CHECKOUT_BASE_URL = os.environ["UPI_GATEWAY_CHECKOUT_URL"]
SUPPORT_FORM_URLS = json.loads(os.environ.get("SUPPORT_FORM_URLS_JSON", "{}"))
DEFAULT_SUPPORT_FORM_URL = os.environ.get("SUPPORT_FORM_URL", "")
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
        "blessing": "Daily Blessing",
        "occasion": "Temple &amp; Occasion Alert",
        "gold": "Gold",
        "silver": "Silver",
        "wow": "WoW [Words of Wisdom]",
        "timing": "Auspicious Timing",
        "weather": "Weather [Plan Your Day]",
        "rain_suffix": " • {pct}% rain chance",
        "caution": "⚠️ <b>CAUTION:</b> Heavy rain / snow / low visibility possible—plan extra travel buffer.",
        "umbrella": "☂️ <b>Umbrella Notice:</b> Carry an umbrella or rain cover before stepping out.",
        "care_caution": "💛 <i>Care: Your safety comes first today—travel unhurriedly.</i>",
        "care_umbrella": "💛 <i>Care: May your steps stay dry, safe, and peaceful today.</i>",
        "care_normal": "💛 <i>Care: Wishing you a calm, healthy, and steady day ahead.</i>",
        "btn_profile": "👤 Profile",
        "btn_settings": "⚙️ Settings",
        "btn_other": "📰 Other Services (12 Pillars & Social)",
        "btn_pay": "💳 Pay (UPI)",
        "btn_support": "🛠️ Support (Suggestion / Complaint)",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "ta": {
        "blessing": "தினசரி ஆசீர்வாதம்",
        "occasion": "கோவில் &amp; விசேஷ அறிவிப்பு",
        "gold": "தங்கம்",
        "silver": "வெள்ளி",
        "wow": "WoW [Words of Wisdom]",
        "timing": "நல்ல நேரம்",
        "weather": "வானிலை [நாளைய திட்டம்]",
        "rain_suffix": " • {pct}% மழை வாய்ப்பு",
        "caution": "⚠️ <b>எச்சரிக்கை:</b> கனமழை / பனி / குறைந்த பார்வை வாய்ப்பு—கவனமாக பயணிக்கவும்.",
        "umbrella": "☂️ <b>குடை அறிவிப்பு:</b> வெளியே செல்லும் முன் குடை எடுத்துச் செல்லவும்.",
        "care_caution": "💛 <i>அக்கறை: உங்கள் பாதுகாப்பே முக்கியம்—அவசரமின்றி பயணிக்கவும்.</i>",
        "care_umbrella": "💛 <i>அக்கறை: இன்று உங்கள் பயணம் பாதுகாப்பாகவும் அமைதியாகவும் அமையட்டும்.</i>",
        "care_normal": "💛 <i>அக்கறை: இன்று அமைதியான, ஆரோக்கியமான நாளாக அமைய வாழ்த்துகள்.</i>",
        "btn_profile": "👤 சுயவிவரம்",
        "btn_settings": "⚙️ அமைப்புகள்",
        "btn_other": "📰 மற்ற சேவைகள் (12 தூண்கள் & சமூகம்)",
        "btn_pay": "💳 UPI மூலம் செலுத்துக",
        "btn_support": "🛠️ உதவி (கருத்து / புகார்)",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "hi": {
        "blessing": "दैनिक आशीर्वाद",
        "occasion": "मंदिर व विशेष पर्व अलर्ट",
        "gold": "सोना",
        "silver": "चांदी",
        "wow": "WoW [Words of Wisdom]",
        "timing": "शुभ समय",
        "weather": "मौसम [दिन की योजना]",
        "rain_suffix": " • {pct}% बारिश की संभावना",
        "caution": "⚠️ <b>सावधानी:</b> भारी बारिश / कोहरा संभव—यात्रा में अतिरिक्त समय रखें।",
        "umbrella": "☂️ <b>छाता सूचना:</b> बाहर निकलने से पहले छाता या रेन कवर साथ रखें।",
        "care_caution": "💛 <i>देखभाल: आपकी सुरक्षा सर्वोपरि है—संभलकर यात्रा करें।</i>",
        "care_umbrella": "💛 <i>देखभाल: आज आपके कदम सुरक्षित और शांतिपूर्ण रहें।</i>",
        "care_normal": "💛 <i>देखभाल: आपका दिन शांत, स्वस्थ और मंगलमय हो।</i>",
        "btn_profile": "👤 प्रोफ़ाइल",
        "btn_settings": "⚙️ सेटिंग्स",
        "btn_other": "📰 अन्य सेवाएं (12 पिलर्स व सोशल)",
        "btn_pay": "💳 UPI से भुगतान करें",
        "btn_support": "🛠️ सहायता (सुझाव / शिकायत)",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "te": {
        "blessing": "రోజువారీ ఆశీర్వాదం",
        "occasion": "ఆలయ &amp; ప్రత్యేక విశేషం",
        "gold": "బంగారం",
        "silver": "వెండి",
        "wow": "WoW [Words of Wisdom]",
        "timing": "శుభ సమయం",
        "weather": "వాతావరణం [రోజు ప్రణాళిక]",
        "rain_suffix": " • {pct}% వర్షం అవకాశం",
        "caution": "⚠️ <b>జాగ్రత్త:</b> భారీ వర్షం / పొగమంచు అవకాశం—జాగ్రత్తగా ప్రయాణించండి.",
        "umbrella": "☂️ <b>గొడుగు సూచన:</b> బయటకు వెళ్లే ముందు గొడుగు వెంట తీసుకెళ్లండి.",
        "care_caution": "💛 <i>శ్రద్ధ: మీ భద్రతే ముఖ్యం—నిదానంగా, సురక్షితంగా ప్రయాణించండి.</i>",
        "care_umbrella": "💛 <i>శ్రద్ధ: నేటి మీ ప్రయాణం సురక్షితంగా, ప్రశాంతంగా సాగుగాక.</i>",
        "care_normal": "💛 <i>శ్రద్ధ: మీకు ప్రశాంతమైన, ఆరోగ్యకరమైన రోజు కలగాలని కోరుకుంటున్నాము.</i>",
        "btn_profile": "👤 ప్రొఫైల్",
        "btn_settings": "⚙️ సెట్టింగ్స్",
        "btn_other": "📰 ఇతర సేవలు (12 పిల్లర్స్ & సోషల్)",
        "btn_pay": "💳 UPI ద్వారా చెల్లించండి",
        "btn_support": "🛠️ సహాయం (సలహా / ఫిర్యాదు)",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "kn": {
        "blessing": "ದೈನಂದಿನ ಆಶೀರ್ವಾದ",
        "occasion": "ದೇವಾಲಯ &amp; ವಿಶೇಷ ಮಾಹಿತಿ",
        "gold": "ಚಿನ್ನ",
        "silver": "ಬೆಳ್ಳಿ",
        "wow": "WoW [Words of Wisdom]",
        "timing": "ಶುಭ ಸಮಯ",
        "weather": "ಹವಾಮಾನ [ದಿನದ ಯೋಜನೆ]",
        "rain_suffix": " • {pct}% ಮಳೆ ಸಾಧ್ಯತೆ",
        "caution": "⚠️ <b>ಎಚ್ಚರಿಕೆ:</b> ಭಾರೀ ಮಳೆ / ಮಂಜು ಸಾಧ್ಯತೆ—ಜಾಗರೂಕತೆಯಿಂದ ಪ್ರಯಾಣಿಸಿ.",
        "umbrella": "☂️ <b>ಛತ್ರಿ ಸೂಚನೆ:</b> ಹೊರಗೆ ಹೋಗುವ ಮುನ್ನ ಛತ್ರಿ ಜೊತೆಯಲ್ಲಿಡಿ.",
        "care_caution": "💛 <i>ಕಾಳಜಿ: ನಿಮ್ಮ ಸುರಕ್ಷತೆಯೇ ಮುಖ್ಯ—ನಿದಾನವಾಗಿ ಪ್ರಯಾಣಿಸಿ.</i>",
        "care_umbrella": "💛 <i>ಕಾಳಜಿ: ಇಂದಿನ ನಿಮ್ಮ ಹೆಜ್ಜೆಗಳು ಸುರಕ್ಷಿತ ಮತ್ತು ಶಾಂತಿಯುತವಾಗಿರಲಿ.</i>",
        "care_normal": "💛 <i>ಕಾಳಜಿ: ನಿಮಗೆ ಶಾಂತ, ಆರೋಗ್ಯಕರ ಮತ್ತು ಶುಭ ದಿನವಾಗಲಿ.</i>",
        "btn_profile": "👤 ಪ್ರೊಫೈಲ್",
        "btn_settings": "⚙️ ಸೆಟ್ಟಿಂಗ್ಸ್",
        "btn_other": "📰 ಇತರೆ ಸೇವೆಗಳು (12 ಪಿಲ್ಲರ್ಸ್ & ಸೋಶಿಯಲ್)",
        "btn_pay": "💳 UPI ಮೂಲಕ ಪಾವತಿಸಿ",
        "btn_support": "🛠️ ಬೆಂಬಲ (ಸಲಹೆ / ದೂರು)",
        "btn_translate": "🌐 Translate [ENG]",
    },
    "ml": {
        "blessing": "ദൈനംദിന അനുഗ്രഹം",
        "occasion": "ക്ഷേത്ര &amp; വിശേഷ അറിയിപ്പ്",
        "gold": "സ്വർണ്ണം",
        "silver": "വെള്ളി",
        "wow": "WoW [Words of Wisdom]",
        "timing": "ശുഭ സമയം",
        "weather": "കാലാവസ്ഥ [ദിവസ ആസൂത്രണം]",
        "rain_suffix": " • {pct}% മഴ സാധ്യത",
        "caution": "⚠️ <b>ജാഗ്രത:</b> കനത്ത മഴ / മൂടൽമഞ്ഞ് സാധ്യത—യാത്രയിൽ ശ്രദ്ധിക്കുക.",
        "umbrella": "☂️ <b>കുട അറിയിപ്പ്:</b> പുറത്തിറങ്ങുന്നതിന് മുൻപ് കുട കരുതുക.",
        "care_caution": "💛 <i>കരുതൽ: നിങ്ങളുടെ സുരക്ഷയാണ് പ്രധാനം—ശ്രദ്ധയോടെ യാത്ര ചെയ്യുക.</i>",
        "care_umbrella": "💛 <i>കരുതൽ: ഇന്നത്തെ യാത്ര സുരക്ഷിതവും സമാധാനപരവുമാകട്ടെ.</i>",
        "care_normal": "💛 <i>കരുതൽ: ശാന്തവും ആരോഗ്യകരവുമായ ഒരു നല്ല ദിവസം ആശംസിക്കുന്നു.</i>",
        "btn_profile": "👤 പ്രൊഫൈൽ",
        "btn_settings": "⚙️ ക്രമീകരണങ്ങൾ",
        "btn_other": "📰 മറ്റ് സേവനങ്ങൾ (12 പില്ലേഴ്സ് & സോഷ്യൽ)",
        "btn_pay": "💳 UPI വഴി പണമടയ്ക്കുക",
        "btn_support": "🛠️ സഹായം (നിർദ്ദേശം / പരാതി)",
        "btn_translate": "🌐 Translate [ENG]",
    },
}


def lbl(lang: str) -> dict:
    return CARD_LABELS.get(lang) or CARD_LABELS["en"]


def normalize_location_key(raw_loc: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]+", "_", raw_loc.upper()).strip("_")
    return cleaned or "CHENNAI"


def build_support_url(telegram_id: int, lang: str) -> str:
    template = SUPPORT_FORM_URLS.get(lang) or SUPPORT_FORM_URLS.get("en") or DEFAULT_SUPPORT_FORM_URL
    if not template:
        return "https://t.me"
    if "{uid}" in template:
        return template.format(uid=telegram_id)
    sep = "&" if "?" in template else "?"
    return f"{template}{sep}uid={telegram_id}"


def build_inline_keyboard_dict(edition_date: str, telegram_id: int, lang: str) -> dict:
    L = lbl(lang)
    upi_url = f"{UPI_CHECKOUT_BASE_URL}?uid={telegram_id}&ref={edition_date}"
    support_url = build_support_url(telegram_id, lang)
    rows = [
        [{"text": f"⭐ {i}", "callback_data": f"rate:{edition_date}:{i}"} for i in range(1, 6)],
        [{"text": L["btn_profile"], "callback_data": "menu:profile"}, {"text": L["btn_settings"], "callback_data": "menu:settings"}],
        [{"text": L["btn_other"], "callback_data": "menu:other_services"}],
        [{"text": L["btn_pay"], "url": upi_url}],
        [{"text": L["btn_support"], "url": support_url}],
    ]
    if lang != "en":
        rows.append([{"text": L["btn_translate"], "callback_data": f"translate:en:{edition_date}"}])
    return {"inline_keyboard": rows}


def build_weather_care_block(city_name: str, city: dict, lang: str) -> str:
    L = lbl(lang)
    weather_raw = str(city.get("weather") or "Pleasant morning").strip()
    rain_prob = city.get("rain_chance_pct")
    if isinstance(rain_prob, str) and rain_prob.isdigit():
        rain_prob = int(rain_prob)
    severity = str(city.get("condition_severity") or "").strip().upper()
    custom_care = str(city.get("care_line") or "").strip()

    prob_suffix = L["rain_suffix"].format(pct=int(rain_prob)) if isinstance(rain_prob, (int, float)) else ""
    lines = [f"🌦️ <b>{L['weather']} — {html.escape(city_name)}:</b> {html.escape(weather_raw)}{html.escape(prob_suffix)}"]

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
        lines.append(L["caution"])
        care = custom_care or L["care_caution"]
    elif is_umbrella:
        lines.append(L["umbrella"])
        care = custom_care or L["care_umbrella"]
    else:
        care = custom_care or L["care_normal"]

    lines.append(care)
    return "\n".join(lines)


def render_caption(
    deity: dict,
    occasion: dict,
    scripture: dict,
    gold: dict,
    rasi_name: str,
    rasi: dict,
    city_name: str,
    city: dict,
    lang: str,
) -> str:
    L = lbl(lang)
    title = html.escape(str(deity.get("title") or L["blessing"]))
    deity_verse = html.escape(str(deity.get("deity_verse") or deity.get("slogan") or ""))

    devotional_lines = [
        f"🪔 <b>{L['blessing']} — {title}</b>",
        deity_verse,
    ]

    sc_source = str(scripture.get("source") or "").strip()
    sc_verse = str(scripture.get("verse") or "").strip()
    sc_meaning = str(scripture.get("meaning") or "").strip()
    if sc_verse and sc_meaning:
        devotional_lines.append(
            f"📜 <b>{html.escape(sc_source)}:</b> <i>{html.escape(sc_verse)}</i> — {html.escape(sc_meaning)}"
        )

    occ_title = str(occasion.get("occasion_title") or occasion.get("title") or "").strip()
    occ_detail = str(occasion.get("occasion_temple") or occasion.get("temple_highlight") or "").strip()
    if occ_detail.lower() not in {"", "none", "special panchangam observance & temple highlights."}:
        occ_head = f"🛕 <b>{html.escape(occ_title)}:</b> " if occ_title else f"🛕 <b>{L['occasion']}:</b> "
        devotional_lines.append(f"{occ_head}{html.escape(occ_detail)}")

    weather_block = build_weather_care_block(city_name, city, lang)
    rate_22k = html.escape(str(gold.get("rate_22k", "N/A")))
    rate_24k = html.escape(str(gold.get("rate_24k", "N/A")))
    rate_silver = html.escape(str(gold.get("rate_silver", "N/A")))
    rasi_words = html.escape(str(rasi.get("three_words", "")))
    auspicious = html.escape(str(city.get("auspicious_time", "")))

    body = (
        f"<b>{AURA_HEADER}</b>\n"
        f"{DIVIDER}\n\n"
        f"{chr(10).join(devotional_lines)}\n\n"
        f"🟡 {L['gold']}: 22K {rate_22k} | 24K {rate_24k} | ⚪ {L['silver']}: {rate_silver}\n\n"
        f"✨ <b>{L['wow']} ({html.escape(rasi_name)}):</b> {rasi_words}\n\n"
        f"⏳ <b>{L['timing']}:</b> {auspicious}\n\n"
        f"{weather_block}"
    )

    max_body = 1024 - len(SHORT_DISCLAIMER) - 4
    if len(body) > max_body:
        body = body[: max_body - 3].rsplit(" ", 1)[0] + "..."
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
    city_raw = (sub["city"] or "Chennai").strip()
    rasi_name = (sub["rasi"] or "Mesham").strip()
    deity_mode = (sub["deity_mode"] or "AUTO").upper()
    deity_key = "DEITY_ALL_OCCASIONS" if deity_mode == "ALL_OCCASIONS" else "DEITY_DAY_OF_WEEK"

    def get_bucket(b_key: str) -> tuple[dict, str | None]:
        item = cache_map.get((lang, b_key)) or cache_map.get(("en", b_key))
        return (item["payload"], item["file_id"]) if item else ({}, None)

    deity, file_id = get_bucket(deity_key)
    if deity_key != "DEITY_DAY_OF_WEEK" and not deity:
        deity, file_id = get_bucket("DEITY_DAY_OF_WEEK")
    if not file_id:
        _, en_fid = get_bucket("DEITY_DAY_OF_WEEK")
        file_id = en_fid

    occasion, _ = get_bucket("DEITY_ALL_OCCASIONS")
    scripture, _ = get_bucket("SCRIPTURE_DAILY")
    gold, _ = get_bucket("GOLD_INR")
    rasi, _ = get_bucket(f"RASI_{rasi_name.upper()}")

    loc_key = normalize_location_key(city_raw)
    city_part = normalize_location_key(city_raw.split(",", 1)[-1])
    city, _ = get_bucket(f"CITY_{loc_key}")
    if not city:
        city, _ = get_bucket(f"CITY_{city_part}")
    if not city:
        city, _ = get_bucket("CITY_CHENNAI")
    display_loc = str(city.get("label") or city_raw or "Chennai")

    caption = render_caption(deity, occasion, scripture, gold, rasi_name, rasi, display_loc, city, lang)
    reply_markup = build_inline_keyboard_dict(edition_date, uid, lang)
    asset_path = deity.get("asset_path", "")

    try:
        if file_id:
            resp = await session.post(
                f"{TELEGRAM_API_BASE}/sendPhoto",
                json={
                    "chat_id": uid,
                    "photo": file_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                    "reply_markup": reply_markup,
                },
                timeout=15,
            )
        elif asset_path and Path(asset_path).is_file():
            form = aiohttp.FormData()
            form.add_field("chat_id", str(uid))
            form.add_field("caption", caption)
            form.add_field("parse_mode", "HTML")
            form.add_field("reply_markup", json.dumps(reply_markup))
            form.add_field("photo", Path(asset_path).read_bytes(), filename=Path(asset_path).name, content_type="image/png")
            resp = await session.post(f"{TELEGRAM_API_BASE}/sendPhoto", data=form, timeout=30)
        else:
            resp = await session.post(
                f"{TELEGRAM_API_BASE}/sendMessage",
                json={
                    "chat_id": uid,
                    "text": caption,
                    "parse_mode": "HTML",
                    "reply_markup": reply_markup,
                },
                timeout=15,
            )

        async with resp:
            if resp.status == 200:
                body = await resp.json()
                photos = body.get("result", {}).get("photo") or []
                if not file_id and photos:
                    new_file_id = photos[-1]["file_id"]
                    for k in list(cache_map.keys()):
                        if k[1] == deity_key:
                            cache_map[k]["file_id"] = new_file_id
                    await pool.execute(
                        "UPDATE daily_shared_cache SET telegram_file_id = $1 WHERE edition_date = $2::date AND bucket_key = $3;",
                        new_file_id,
                        edition_date,
                        deity_key,
                    )
                return True
            if resp.status == 403:
                await pool.execute("UPDATE subscribers SET is_active = FALSE, updated_at = NOW() WHERE telegram_id = $1;", uid)
            elif resp.status == 429:
                body = await resp.json()
                await asyncio.sleep(int(body.get("parameters", {}).get("retry_after", 3)))
    except Exception:
        pass
    return False


async def run_broadcast() -> None:
    edition_date = datetime.now(IST).strftime("%Y-%m-%d")
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    try:
        rows = await pool.fetch(
            "SELECT language, bucket_key, payload_json, telegram_file_id FROM daily_shared_cache WHERE edition_date = $1::date;",
            edition_date,
        )
        cache_map = {
            (r["language"], r["bucket_key"]): {
                "payload": json.loads(r["payload_json"]) if isinstance(r["payload_json"], str) else r["payload_json"],
                "file_id": r["telegram_file_id"],
            }
            for r in rows
        }
        subs = await pool.fetch("SELECT telegram_id, preferred_language, city, rasi, deity_mode FROM subscribers WHERE is_active = TRUE;")
        sent = 0
        async with aiohttp.ClientSession() as session:
            for i in range(0, len(subs), BATCH_CONCURRENCY):
                batch = subs[i : i + BATCH_CONCURRENCY]
                results = await asyncio.gather(*(send_to_subscriber(session, pool, s, cache_map, edition_date) for s in batch))
                sent += sum(1 for ok in results if ok)
                await asyncio.sleep(1.05)
        print(f"[{edition_date}] AURA Broadcast complete: {sent}/{len(subs)} delivered.")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run_broadcast())
