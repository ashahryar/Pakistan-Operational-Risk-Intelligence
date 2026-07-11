from bs4 import BeautifulSoup

# Urdu city name → English transliteration mapping
URDU_CITY_MAP = {
    "اسلام آباد": "Islamabad",
    "کوئٹہ سمنگلی": "Quetta Samungli",
    "گوادر": "Gwadar",
    "قلات": "Kalat",
    "تربت": "Turbat",
    "جيوانى": "Jiwani",
    "سبی": "Sibi",
    "نوکنڈی": "Nokundi",
    "مری": "Murree",
    "بہاولپور": "Bahawalpur",
    "ڈیرہ غازی خان": "Dera Ghazi Khan",
    "ملتان": "Multan",
    "چکوال": "Chakwal",
    "فیصل آباد": "Faisalabad",
    "سرگودھا": "Sargodha",
    "لاہور": "Lahore",
    "اٹک": "Attock",
    "راولپنڈی": "Rawalpindi",
    "جہلم": "Jhelum",
    "ساہیوال": "Sahiwal",
    "کراچی": "Karachi",
    "حیدر آباد": "Hyderabad",
    "سکھر": "Sukkur",
    "ٹھٹھہ": "Thatta",
    "موہنجوڈاڑو": "Mohenjo Daro",
    "دادو": "Dadu",
    "مٹھی": "Mithi",
    "نوابشاہ": "Nawabshah",
    "چترال": "Chitral",
    "دیر": "Dir",
    "مالم جبہ": "Malam Jabba",
    "سیدوشریف": "Saidu Sharif",
    "پشاور": "Peshawar",
    "بنوں": "Bannu",
    "ڈیرہ اسماعیل خان": "Dera Ismail Khan",
    "ایبٹ آباد": "Abbottabad",
    "گلگت": "Gilgit",
    "سکردو": "Skardu",
    "استور": "Astore",
    "ہنزہ": "Hunza",
    "گوپس": "Gupis",
    "بونجی": "Bunji",
    "چلاس": "Chilas",
    "بابو سر پاس": "Babusar Pass",
    "راولاکوٹ": "Rawalakot",
    "شو پیاں": "Shopian",
    "اننت ناگ": "Anantnag",
    "پلوامہ": "Pulwama",
    "لہہ": "Leh",
    "سری نگر": "Srinagar",
    "جموں": "Jammu",
    "گڑھی دوپٹہ": "Garhi Dupatta",
    "مظفر آباد": "Muzaffarabad",
    "بارہ مو لہ": "Baramulla",
}


def transliterate_city(name: str) -> str:
    """Return English name if Urdu mapping exists, else return original."""
    return URDU_CITY_MAP.get(name.strip(), name.strip())


def extract_forecast_text(soup: BeautifulSoup):

    blocks = []

    for div in soup.select("div.well h5"):
        text = div.get_text(" ", strip=True)
        if text:
            blocks.append(text)

    if not blocks:
        for p in soup.find_all("p"):
            text = p.get_text(" ", strip=True)
            if (
                text
                and "Disclaimer:" not in text
                and "Pakistan Meteorological Department" not in text
                and "©" not in text
                and (len(text) > 30 or any(kw in text.lower() for kw in ["rain", "storm", "thunder", "weather", "alert", "wind", "temp"]))
            ):
                blocks.append(text)

    return "\n".join(blocks)


def extract_tables(soup: BeautifulSoup):
    """Extract tables and transliterate city names from Urdu to English."""
    tables = []

    for table in soup.select("table"):

        head = table.find("tr")
        if not head:
            continue

        headers = [th.get_text(strip=True) for th in head.find_all(["th", "td"])]

        rows = []
        for tr in table.find_all("tr")[1:]:
            cols = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if cols:
                # Last column is typically the city name — transliterate it
                if len(cols) >= 1:
                    cols[-1] = transliterate_city(cols[-1])
                rows.append(cols)

        if rows:
            tables.append({"headers": headers, "rows": rows})

    return tables


def extract_structured_weather(tables: list) -> list:
    """
    Convert raw PMD table rows into structured dicts with named fields.
    Expected column order: day3_forecast, day2_forecast, day1_forecast,
                           max_temperature, humidity, city
    """
    records = []
    for table in tables:
        for row in table.get("rows", []):
            if len(row) < 6:
                continue
            records.append({
                "city": row[5],
                "humidity": row[4],
                "max_temperature": row[3],
                "day1_forecast": row[2],
                "day2_forecast": row[1],
                "day3_forecast": row[0],
            })
    return records
