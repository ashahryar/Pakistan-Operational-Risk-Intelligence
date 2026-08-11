from validation.mappings import CITY_MAPPING


def normalize_city(city: str):

    city = (city or "").strip()

    return CITY_MAPPING.get(
        city,
        {
            "city": city,
            "province": "Unknown",
            "district": "Unknown",
        },
    )

"""
validation/translator.py
"""

CITY_TRANSLATIONS = {

    # Islamabad
    "اسلام آباد": "Islamabad",
    "اسلام آباد": "Islamabad",

    # Punjab
    "لاہور": "Lahore",
    "فیصل آباد": "Faisalabad",
    "فیصل آباد": "Faisalabad",
    "ملتان": "Multan",
    "بہاولپور": "Bahawalpur",
    "سرگودھا": "Sargodha",
    "ساہیوال": "Sahiwal",
    "راولپنڈی": "Rawalpindi",
    "جہلم": "Jhelum",
    "چکوال": "Chakwal",
    "اٹک": "Attock",
    "ڈیرہ غازی خان": "Dera Ghazi Khan",

    # Sindh
    "کراچی": "Karachi",
    "حیدر آباد": "Hyderabad",
    "حیدر آباد": "Hyderabad",
    "سکھر": "Sukkur",
    "لاڑکانہ": "Larkana",
    "دادو": "Dadu",
    "جیکب آباد": "Jacobabad",
    "جیکب آباد": "Jacobabad",
    "شکارپور": "Shikarpur",

    # Balochistan
    "کوئٹہ": "Quetta",
    "کوئٹہ سمنگلی": "Quetta Samungli",
    "گوادر": "Gwadar",
    "قلات": "Kalat",
    "تربت": "Turbat",
    "جیوانی": "Jiwani",
    "جيوانى": "Jiwani",
    "سبی": "Sibi",
    "نوکنڈی": "Nokundi",

    # KP
    "پشاور": "Peshawar",
    "ڈی آئی خان": "Dera Ismail Khan",
    "ڈی آئی خان": "Dera Ismail Khan",
    "بنوں": "Bannu",
    "چترال": "Chitral",
    "سوات": "Swat",
    "کالام": "Kalam",
    "دیر": "Dir",

    # AJK
    "مظفر آباد": "Muzaffarabad",
    "مظفر آباد": "Muzaffarabad",
    "گڑھی دوپٹہ": "Garhi Dupatta",
    "راولاکوٹ": "Rawalakot",

    # GB
    "گلگت": "Gilgit",
    "سکردو": "Skardu",

    # Others
    "مری": "Murree",
    "لہہ": "Leh",
    "جموں": "Jammu",
    "سری نگر": "Srinagar",
    "پلوامہ": "Pulwama",
    "شوپیاں": "Shopian",
    "شو پیاں": "Shopian",
    "بارہ مولہ": "Baramulla",
    "بارہ مو لہ": "Baramulla",
    "اننت ناگ": "Anantnag",
}


CITY_INFO = {

    "Islamabad": ("Islamabad Capital Territory", "Islamabad"),

    "Lahore": ("Punjab", "Lahore"),
    "Faisalabad": ("Punjab", "Faisalabad"),
    "Multan": ("Punjab", "Multan"),
    "Bahawalpur": ("Punjab", "Bahawalpur"),
    "Sargodha": ("Punjab", "Sargodha"),
    "Sahiwal": ("Punjab", "Sahiwal"),
    "Rawalpindi": ("Punjab", "Rawalpindi"),
    "Jhelum": ("Punjab", "Jhelum"),
    "Chakwal": ("Punjab", "Chakwal"),
    "Attock": ("Punjab", "Attock"),
    "Dera Ghazi Khan": ("Punjab", "Dera Ghazi Khan"),

    "Karachi": ("Sindh", "Karachi"),
    "Hyderabad": ("Sindh", "Hyderabad"),
    "Sukkur": ("Sindh", "Sukkur"),
    "Larkana": ("Sindh", "Larkana"),
    "Dadu": ("Sindh", "Dadu"),
    "Jacobabad": ("Sindh", "Jacobabad"),
    "Shikarpur": ("Sindh", "Shikarpur"),

    "Quetta": ("Balochistan", "Quetta"),
    "Quetta Samungli": ("Balochistan", "Quetta"),
    "Gwadar": ("Balochistan", "Gwadar"),
    "Kalat": ("Balochistan", "Kalat"),
    "Turbat": ("Balochistan", "Kech"),
    "Jiwani": ("Balochistan", "Gwadar"),
    "Sibi": ("Balochistan", "Sibi"),
    "Nokundi": ("Balochistan", "Chagai"),

    "Peshawar": ("Khyber Pakhtunkhwa", "Peshawar"),
    "Dera Ismail Khan": ("Khyber Pakhtunkhwa", "Dera Ismail Khan"),
    "Bannu": ("Khyber Pakhtunkhwa", "Bannu"),
    "Chitral": ("Khyber Pakhtunkhwa", "Upper Chitral"),
    "Swat": ("Khyber Pakhtunkhwa", "Swat"),
    "Kalam": ("Khyber Pakhtunkhwa", "Swat"),
    "Dir": ("Khyber Pakhtunkhwa", "Upper Dir"),

    "Muzaffarabad": ("AJK", "Muzaffarabad"),
    "Garhi Dupatta": ("AJK", "Muzaffarabad"),
    "Rawalakot": ("AJK", "Poonch"),

    "Gilgit": ("Gilgit Baltistan", "Gilgit"),
    "Skardu": ("Gilgit Baltistan", "Skardu"),
}


def normalize_city(city: str) -> str:
    city = city.strip()
    return CITY_TRANSLATIONS.get(city, city)


def province_from_city(city: str) -> str:
    city = normalize_city(city)
    return CITY_INFO.get(city, ("Unknown", None))[0]


def district_from_city(city: str):
    city = normalize_city(city)
    return CITY_INFO.get(city, ("Unknown", None))[1]