import json
import re
from pathlib import Path

from scripts.parsing.pmd.utils import clean_text

RAW_FILE = Path("data/raw/pmd/reports/weather_alerts/all/latest.json")


REGIONS = {
    "Punjab": ["Lahore", "Kasur", "Okara", "Pakpattan", "Jhang",
                "Sahiwal", "Khanewal", "Vehari", "Multan",
                "Layyah", "Faisalabad", "Attock", "Chakwal",
                "Talagang", "Jhelum", "Sargodha",
                "Bhakkar", "Mianwali", "Dera Ghazi Khan"],

    "Sindh": ["Karachi", "Hyderabad", "Thatta", "Badin",
               "Sukkur", "Larkana"],

    "Khyber Pakhtunkhwa": ["Peshawar", "Swat", "Dir", "Chitral",
                            "Abbottabad", "Haripur", "Bannu",
                            "Kohat", "Karak", "Mardan",
                            "Charsadda", "Nowshera"],

    "Balochistan": ["Quetta", "Zhob", "Barkhan",
                     "Musakhel", "Gwadar"],

    "Gilgit Baltistan": ["Gilgit", "Skardu"],

    "AJK": ["Kashmir", "Muzaffarabad"],

    "Islamabad": ["Islamabad"]
}


def detect_alert_type(text):

    text = text.lower()

    if "rain" in text:
        return "Rain"

    if "thunder" in text:
        return "Thunderstorm"

    if "windstorm" in text:
        return "Windstorm"

    if "heat" in text:
        return "Heatwave"

    if "snow" in text:
        return "Snow"

    return "Weather Alert"


def detect_severity(text):

    text = text.lower()

    if "very heavy" in text:
        return "Very Heavy"

    if "heavy" in text:
        return "Heavy"

    if "moderate" in text:
        return "Moderate"

    if "light" in text:
        return "Light"

    return "Normal"


def extract_duration(text):

    match = re.search(r"\d+\s*-\s*\d+\s*hrs?", text.lower())

    if match:
        return match.group()

    return None


def extract_regions(text):

    regions = []

    for province, cities in REGIONS.items():

        for city in cities:

            if city.lower() in text.lower():

                regions.append(province)

                break

    return sorted(set(regions))


def parse_weather_alert():

    with open(RAW_FILE, encoding="utf-8") as f:

        raw = json.load(f)

    forecast = clean_text(raw["forecast"])

    result = {

        "alert_type": detect_alert_type(forecast),

        "severity": detect_severity(forecast),

        "duration": extract_duration(forecast),

        "regions": extract_regions(forecast),

        "forecast": forecast,

        "category": raw["category"],

        "scraped_at": raw["scraped_at"]

    }

    return result


if __name__ == "__main__":

    parsed = parse_weather_alert()

    print(json.dumps(parsed, indent=4))