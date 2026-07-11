"""
PMD Utility Functions
"""

import re
from datetime import datetime


def clean_text(text):

    if text is None:
        return ""

    text = re.sub(r"\s+", " ", str(text))

    return text.strip()


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


def province_from_city(city):

    city = city.strip()

    mapping = {

        "اسلام آباد": "Islamabad",

        "کراچی": "Sindh",
        "حیدر آباد": "Sindh",
        "ٹھٹھہ": "Sindh",
        "دادو": "Sindh",
        "سکھر": "Sindh",
        "نوابشاہ": "Sindh",
        "مٹھی": "Sindh",

        "لاہور": "Punjab",
        "فیصل آباد": "Punjab",
        "راولپنڈی": "Punjab",
        "جہلم": "Punjab",
        "ملتان": "Punjab",
        "بہاولپور": "Punjab",
        "ساہیوال": "Punjab",
        "چکوال": "Punjab",
        "اٹک": "Punjab",
        "سرگودھا": "Punjab",
        "ڈیرہ غازی خان": "Punjab",

        "پشاور": "Khyber Pakhtunkhwa",
        "ایبٹ آباد": "Khyber Pakhtunkhwa",
        "بنوں": "Khyber Pakhtunkhwa",
        "سوات": "Khyber Pakhtunkhwa",
        "دیر": "Khyber Pakhtunkhwa",
        "چترال": "Khyber Pakhtunkhwa",

        "کوئٹہ سمنگلی": "Balochistan",
        "تربت": "Balochistan",
        "قلات": "Balochistan",
        "سبی": "Balochistan",
        "گوادر": "Balochistan",

        "گلگت": "Gilgit Baltistan",
        "سکردو": "Gilgit Baltistan",
        "استور": "Gilgit Baltistan",
        "ہنزہ": "Gilgit Baltistan",

        "مظفر آباد": "AJK",
        "راولاکوٹ": "AJK",
        "گڑھی دوپٹہ": "AJK"

    }

    return mapping.get(city, "Unknown")


def today():

    return datetime.now().isoformat()