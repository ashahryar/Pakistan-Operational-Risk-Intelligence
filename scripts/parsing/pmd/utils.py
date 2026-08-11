"""
PMD Utility Functions
"""

import re
from datetime import datetime


# ==========================================================
# TEXT
# ==========================================================

def clean_text(text):

    if text is None:
        return ""

    text = re.sub(r"\s+", " ", str(text))

    return text.strip()


# ==========================================================
# NUMBER
# ==========================================================

def extract_number(text):

    if text is None:
        return None

    match = re.search(r"\d+(\.\d+)?", str(text))

    if match:
        try:
            return float(match.group())
        except ValueError:
            return None

    return None


# ==========================================================
# CITY -> PROVINCE
# ==========================================================

CITY_PROVINCE = {

    # Islamabad
    "Islamabad": "Islamabad",

    # Punjab
    "Lahore": "Punjab",
    "Faisalabad": "Punjab",
    "Rawalpindi": "Punjab",
    "Jhelum": "Punjab",
    "Multan": "Punjab",
    "Bahawalpur": "Punjab",
    "Sahiwal": "Punjab",
    "Chakwal": "Punjab",
    "Attock": "Punjab",
    "Sargodha": "Punjab",
    "Dera Ghazi Khan": "Punjab",
    "Murree": "Punjab",

    # Sindh
    "Karachi": "Sindh",
    "Hyderabad": "Sindh",
    "Thatta": "Sindh",
    "Dadu": "Sindh",
    "Sukkur": "Sindh",
    "Nawabshah": "Sindh",
    "Mithi": "Sindh",

    # KP
    "Peshawar": "Khyber Pakhtunkhwa",
    "Abbottabad": "Khyber Pakhtunkhwa",
    "Bannu": "Khyber Pakhtunkhwa",
    "Swat": "Khyber Pakhtunkhwa",
    "Dir": "Khyber Pakhtunkhwa",
    "Chitral": "Khyber Pakhtunkhwa",

    # Balochistan
    "Quetta": "Balochistan",
    "Quetta Samungli": "Balochistan",
    "Gwadar": "Balochistan",
    "Turbat": "Balochistan",
    "Kalat": "Balochistan",
    "Sibi": "Balochistan",
    "Nokundi": "Balochistan",
    "Jiwani": "Balochistan",

    # GB
    "Gilgit": "Gilgit Baltistan",
    "Skardu": "Gilgit Baltistan",
    "Astore": "Gilgit Baltistan",
    "Hunza": "Gilgit Baltistan",

    # AJK
    "Muzaffarabad": "AJK",
    "Rawalakot": "AJK",
    "Garhi Dupatta": "AJK",
}


def province_from_city(city):

    return CITY_PROVINCE.get(city, "Unknown")


# ==========================================================
# CITY -> DISTRICT
# ==========================================================

CITY_DISTRICT = {

    "Islamabad": "Islamabad",

    "Lahore": "Lahore",
    "Faisalabad": "Faisalabad",
    "Rawalpindi": "Rawalpindi",
    "Jhelum": "Jhelum",
    "Multan": "Multan",
    "Bahawalpur": "Bahawalpur",
    "Sahiwal": "Sahiwal",
    "Attock": "Attock",
    "Chakwal": "Chakwal",
    "Sargodha": "Sargodha",
    "Murree": "Murree",
    "Dera Ghazi Khan": "Dera Ghazi Khan",

    "Karachi": "Karachi",
    "Hyderabad": "Hyderabad",
    "Sukkur": "Sukkur",
    "Thatta": "Thatta",
    "Dadu": "Dadu",
    "Mithi": "Tharparkar",
    "Nawabshah": "Shaheed Benazirabad",

    "Peshawar": "Peshawar",
    "Abbottabad": "Abbottabad",
    "Swat": "Swat",
    "Dir": "Upper Dir",
    "Bannu": "Bannu",
    "Chitral": "Chitral",

    "Quetta": "Quetta",
    "Quetta Samungli": "Quetta",
    "Gwadar": "Gwadar",
    "Turbat": "Kech",
    "Kalat": "Kalat",
    "Sibi": "Sibi",
    "Nokundi": "Chagai",
    "Jiwani": "Gwadar",

    "Gilgit": "Gilgit",
    "Skardu": "Skardu",
    "Hunza": "Hunza",
    "Astore": "Astore",

    "Muzaffarabad": "Muzaffarabad",
    "Rawalakot": "Poonch",
    "Garhi Dupatta": "Muzaffarabad",
}


def district_from_city(city):

    return CITY_DISTRICT.get(city)


# ==========================================================
# DATE
# ==========================================================

def today():

    return datetime.now().isoformat()