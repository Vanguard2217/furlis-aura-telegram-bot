import html

SHORT_DISCLAIMER = (
    "⚖️ <i>Disclaimer: Devotional, astrology, gold/market, weather &amp; alert info is for general "
    "guidance only—not financial, medical, travel, or safety advice. Verify critical decisions independently.</i>"
)

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
        lines.append("⚠️ <b>CAUTION:</b> Heavy rain / snow / low visibility possible—plan extra travel buffer and move carefully.")
        care = custom_care or "💛 <i>Care: Your safety comes first today—stay sheltered where needed and travel unhurriedly.</i>"
    elif is_umbrella:
        lines.append("☂️ <b>Umbrella Notice:</b> Carry an umbrella or light rain cover before stepping out.")
        care = custom_care or "💛 <i>Care: May your steps stay dry, safe, and peaceful as you head out today.</i>"
    else:
        care = custom_care or "💛 <i>Care: Wishing you a calm, healthy, and steady day ahead.</i>"

    lines.append(care)
    return "\n".join(lines)

def render_caption(
    deity: dict,
    occasion: dict,
    gold: dict,
    rasi_name: str,
    rasi: dict,
    city_name: str,
    city: dict,
    quote_block: dict,
) -> str:
    title = html.escape(str(deity.get("title") or "Daily Morning Blessing"))
    slogan = html.escape(str(deity.get("slogan") or ""))
    devotional_lines = [f"🪔 <b>{title}</b>", f"<i>{slogan}</i>"]

    occ_title = str(occasion.get("occasion_title") or occasion.get("title") or "").strip()
    occ_detail = str(occasion.get("occasion_temple") or occasion.get("temple_highlight") or "").strip()
    if occ_detail.lower() not in {"", "none", "special panchangam observance & temple highlights."}:
        occ_head = f"🛕 <b>{html.escape(occ_title)}:</b> " if occ_title else "🛕 <b>Occasion &amp; Temple Alert:</b> "
        devotional_lines.append(f"{occ_head}{html.escape(occ_detail)}")

    weather_block = build_weather_care_block(city_name, city)
    rate_22k = html.escape(str(gold.get("rate_22k", "N/A")))
    rate_24k = html.escape(str(gold.get("rate_24k", "N/A")))
    rasi_words = html.escape(str(rasi.get("three_words", "")))
    auspicious = html.escape(str(city.get("auspicious_time", "")))
    quote = html.escape(str(quote_block.get("quote", "")))
    author = html.escape(str(quote_block.get("author", "")))

    body = (
        f"☀️ <b>FURLIS AURA</b>\n\n"
        f"{chr(10).join(devotional_lines)}\n\n"
        f"🪙 <b>Gold:</b> 22K {rate_22k} | 24K {rate_24k}\n"
        f"✨ <b>{html.escape(rasi_name)}:</b> {rasi_words}\n"
        f"⏳ <b>Auspicious:</b> {auspicious}\n"
        f"{weather_block}\n\n"
        f"💡 <i>\"{quote}\"</i> — {author}"
    )

    max_body = 1024 - len(SHORT_DISCLAIMER) - 4
    if len(body) > max_body:
        body = body[: max_body - 3].rsplit(" ", 1)[0] + "..."
    return f"{body}\n\n{SHORT_DISCLAIMER}"
