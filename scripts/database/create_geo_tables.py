"""
scripts/database/create_geo_tables.py

Creates and seeds the geo_locations table in PostgreSQL.

Why this matters:
  Every business question in this platform has a geographic dimension.
  "Where are floods increasing?" requires coordinates.
  "Which districts are high risk?" requires map rendering.
  This table is the single source of truth for all lat/lon lookups
  used by the dashboard map and future GIS features.

Covers:
  - All Punjab districts (PDMA rainfall stations map to these)
  - All major rivers monitored by PDMA gauge reports
  - All PMD weather cities
  - Key NDMA provinces

Run:
  python scripts/database/create_geo_tables.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text
from config.database import engine

# ----------------------------------------------------------
# DDL
# ----------------------------------------------------------

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS geo_locations (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL,
    name_alt     TEXT,
    location_type TEXT NOT NULL,
    province     TEXT,
    country      TEXT DEFAULT 'Pakistan',
    latitude     DOUBLE PRECISION NOT NULL,
    longitude    DOUBLE PRECISION NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, location_type)
);
"""

CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_geo_name ON geo_locations(name);
CREATE INDEX IF NOT EXISTS idx_geo_type ON geo_locations(location_type);
CREATE INDEX IF NOT EXISTS idx_geo_province ON geo_locations(province);
"""

# ----------------------------------------------------------
# SEED DATA
# location_type: district | river | city | province | gauge_station
# ----------------------------------------------------------

LOCATIONS = [

    # ======================================================
    # PUNJAB DISTRICTS  (PDMA rainfall stations)
    # ======================================================
    ("Attock",          "Attock",       "district", "Punjab",       33.7667, 72.3667),
    ("Bahawalnagar",    "Bahawalnagar", "district", "Punjab",       29.9956, 73.2536),
    ("Bahawalpur",      "Bahawalpur",   "district", "Punjab",       29.3956, 71.6722),
    ("Bhakkar",         "Bhakkar",      "district", "Punjab",       31.6278, 71.0644),
    ("Chakwal",         "Chakwal",      "district", "Punjab",       32.9328, 72.8528),
    ("Chiniot",         "Chiniot",      "district", "Punjab",       31.7200, 72.9800),
    ("D.G. Khan",       "Dera Ghazi Khan", "district", "Punjab",   30.0500, 70.6333),
    ("Faisalabad",      "Faisalabad",   "district", "Punjab",       31.4180, 73.0790),
    ("Fort Munro",      "Fort Munro",   "district", "Punjab",       29.8667, 70.1833),
    ("Gujranwala",      "Gujranwala",   "district", "Punjab",       32.1617, 74.1883),
    ("Gujrat",          "Gujrat",       "district", "Punjab",       32.5736, 74.0789),
    ("Hafizabad",       "Hafizabad",    "district", "Punjab",       32.0711, 73.6883),
    ("Jhang",           "Jhang",        "district", "Punjab",       31.2681, 72.3181),
    ("Jhelum",          "Jhelum",       "district", "Punjab",       32.9361, 73.7261),
    ("Joharabad",       "Joharabad",    "district", "Punjab",       32.2667, 72.6333),
    ("Kamra",           "Kamra",        "district", "Punjab",       33.8667, 72.4000),
    ("Kasur",           "Kasur",        "district", "Punjab",       31.1167, 74.4500),
    ("Khanewal",        "Khanewal",     "district", "Punjab",       30.3000, 71.9333),
    ("Khanpur",         "Khanpur",      "district", "Punjab",       28.6472, 70.6556),
    ("Khushab",         "Khushab",      "district", "Punjab",       32.2972, 72.3528),
    ("Kot Addu",        "Kot Addu",     "district", "Punjab",       30.4667, 70.9667),
    ("Lahore",          "Lahore",       "district", "Punjab",       31.5497, 74.3436),
    ("Layyah",          "Layyah",       "district", "Punjab",       30.9597, 70.9397),
    ("Mandi Bahauddin", "Mandi Bahauddin", "district", "Punjab",   32.5864, 73.4917),
    ("Mangla",          "Mangla",       "district", "Punjab",       33.1333, 73.6500),
    ("Mianwali",        "Mianwali",     "district", "Punjab",       32.5853, 71.5436),
    ("Multan",          "Multan",       "district", "Punjab",       30.1978, 71.4711),
    ("Murree",          "Murree",       "district", "Punjab",       33.9042, 73.3903),
    ("Muzaffarabad",    "Muzaffarabad", "district", "AJK",          34.3700, 73.4700),
    ("Narowal",         "Narowal",      "district", "Punjab",       32.1000, 74.8667),
    ("Noor Pur Thal",   "Noorpur Thal", "district", "Punjab",       31.5833, 71.9000),
    ("Okara",           "Okara",        "district", "Punjab",       30.8100, 73.4500),
    ("R.Y. Khan",       "Rahim Yar Khan", "district", "Punjab",    28.4200, 70.2958),
    ("Rajanpur",        "Rajanpur",     "district", "Punjab",       29.1044, 70.3297),
    ("Rawalakot",       "Rawalakot",    "district", "AJK",          33.8578, 73.7614),
    ("Rawalpindi",      "Rawalpindi",   "district", "Punjab",       33.5651, 73.0169),
    ("Sahiwal",         "Sahiwal",      "district", "Punjab",       30.6706, 73.1064),
    ("Sargodha",        "Sargodha",     "district", "Punjab",       32.0836, 72.6711),
    ("Sheikhupura",     "Sheikhupura",  "district", "Punjab",       31.7131, 73.9850),
    ("Sialkot",         "Sialkot",      "district", "Punjab",       32.4945, 74.5229),
    ("Toba Tek Singh",  "Toba Tek Singh", "district", "Punjab",    30.9667, 72.4833),
    ("Wazirabad",       "Wazirabad",    "district", "Punjab",       32.4431, 74.1197),

    # ======================================================
    # RIVERS  (PDMA gauge reports)
    # ======================================================
    ("INDUS",   "Indus River",  "river", "Multiple", 29.3667, 70.8833),
    ("JHELUM",  "Jhelum River", "river", "Punjab",   32.9361, 73.7261),
    ("CHENAB",  "Chenab River", "river", "Punjab",   31.5500, 72.9833),
    ("RAVI",    "Ravi River",   "river", "Punjab",   31.5497, 74.3436),
    ("SUTLEJ",  "Sutlej River", "river", "Punjab",   30.3500, 71.6833),

    # ======================================================
    # PMD WEATHER CITIES  (from pmd_parser.py URDU_CITY_MAP)
    # ======================================================
    ("Islamabad",       "Islamabad",        "city", "ICT",          33.7294, 73.0931),
    ("Karachi",         "Karachi",          "city", "Sindh",        24.8607, 67.0011),
    ("Lahore",          "Lahore",           "city", "Punjab",       31.5497, 74.3436),
    ("Peshawar",        "Peshawar",         "city", "KP",           34.0151, 71.5249),
    ("Quetta Samungli", "Quetta",           "city", "Balochistan",  30.1798, 66.9750),
    ("Multan",          "Multan",           "city", "Punjab",       30.1978, 71.4711),
    ("Faisalabad",      "Faisalabad",       "city", "Punjab",       31.4180, 73.0790),
    ("Rawalpindi",      "Rawalpindi",       "city", "Punjab",       33.5651, 73.0169),
    ("Hyderabad",       "Hyderabad",        "city", "Sindh",        25.3960, 68.3578),
    ("Sukkur",          "Sukkur",           "city", "Sindh",        27.7052, 68.8574),
    ("Bahawalpur",      "Bahawalpur",       "city", "Punjab",       29.3956, 71.6722),
    ("Dera Ghazi Khan", "Dera Ghazi Khan",  "city", "Punjab",       30.0500, 70.6333),
    ("Sargodha",        "Sargodha",         "city", "Punjab",       32.0836, 72.6711),
    ("Sialkot",         "Sialkot",          "city", "Punjab",       32.4945, 74.5229),
    ("Gujranwala",      "Gujranwala",       "city", "Punjab",       32.1617, 74.1883),
    ("Abbottabad",      "Abbottabad",       "city", "KP",           34.1558, 73.2194),
    ("Murree",          "Murree",           "city", "Punjab",       33.9042, 73.3903),
    ("Chitral",         "Chitral",          "city", "KP",           35.8511, 71.7864),
    ("Dir",             "Dir",              "city", "KP",           35.2000, 71.8833),
    ("Gilgit",          "Gilgit",           "city", "GB",           35.9208, 74.3083),
    ("Skardu",          "Skardu",           "city", "GB",           35.2972, 75.6333),
    ("Muzaffarabad",    "Muzaffarabad",     "city", "AJK",          34.3700, 73.4700),
    ("Turbat",          "Turbat",           "city", "Balochistan",  26.0022, 63.0422),
    ("Gwadar",          "Gwadar",           "city", "Balochistan",  25.1264, 62.3225),
    ("Sibi",            "Sibi",             "city", "Balochistan",  29.5436, 67.8775),
    ("Dera Ismail Khan","Dera Ismail Khan", "city", "KP",           31.8314, 70.9019),
    ("Bannu",           "Bannu",            "city", "KP",           32.9889, 70.6044),
    ("Saidu Sharif",    "Saidu Sharif",     "city", "KP",           34.7500, 72.3500),
    ("Astore",          "Astore",           "city", "GB",           35.3667, 74.9000),
    ("Hunza",           "Hunza",            "city", "GB",           36.3167, 74.6500),
    ("Chilas",          "Chilas",           "city", "GB",           35.4167, 74.1000),
    ("Nawabshah",       "Nawabshah",        "city", "Sindh",        26.2442, 68.4100),
    ("Mithi",           "Mithi",            "city", "Sindh",        24.7333, 69.8000),
    ("Dadu",            "Dadu",             "city", "Sindh",        26.7319, 67.7764),
    ("Thatta",          "Thatta",           "city", "Sindh",        24.7461, 67.9239),
    ("Mohenjo Daro",    "Mohenjo Daro",     "city", "Sindh",        27.3244, 68.1378),
    ("Jiwani",          "Jiwani",           "city", "Balochistan",  25.0500, 61.7333),
    ("Nokundi",         "Nokundi",          "city", "Balochistan",  28.8167, 62.7500),
    ("Kalat",           "Kalat",            "city", "Balochistan",  29.0233, 66.5897),

    # ======================================================
    # PROVINCES  (NDMA reports)
    # ======================================================
    ("Punjab",              "Punjab",           "province", "Punjab",       30.9700, 72.6800),
    ("Sindh",               "Sindh",            "province", "Sindh",        26.0000, 68.5000),
    ("Balochistan",         "Balochistan",      "province", "Balochistan",  28.4907, 65.0958),
    ("Khyber Pakhtunkhwa",  "KP",               "province", "KP",           34.0000, 71.5000),
    ("KP",                  "Khyber Pakhtunkhwa","province","KP",           34.0000, 71.5000),
    ("Gilgit Baltistan",    "GB",               "province", "GB",           35.8022, 74.9833),
    ("GB",                  "Gilgit Baltistan", "province", "GB",           35.8022, 74.9833),
    ("AJK",                 "Azad Kashmir",     "province", "AJK",          33.9194, 73.7833),
    ("ICT",                 "Islamabad",        "province", "ICT",          33.7294, 73.0931),
]


def create_geo_table():
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE))
        for stmt in CREATE_INDEX.strip().split("\n"):
            if stmt.strip():
                conn.execute(text(stmt.strip()))
    print("  geo_locations table created.")


def seed_locations():
    inserted = 0
    skipped  = 0

    with engine.begin() as conn:
        for (name, name_alt, loc_type, province, lat, lon) in LOCATIONS:
            result = conn.execute(
                text("""
                    INSERT INTO geo_locations
                        (name, name_alt, location_type, province, latitude, longitude)
                    VALUES
                        (:name, :name_alt, :location_type, :province, :latitude, :longitude)
                    ON CONFLICT (name, location_type) DO NOTHING
                """),
                {
                    "name":          name,
                    "name_alt":      name_alt,
                    "location_type": loc_type,
                    "province":      province,
                    "latitude":      lat,
                    "longitude":     lon,
                },
            )
            if result.rowcount > 0:
                inserted += 1
            else:
                skipped += 1

    return inserted, skipped


def main():
    print("=" * 60)
    print("CREATING GEO_LOCATIONS TABLE")
    print("=" * 60)

    create_geo_table()
    inserted, skipped = seed_locations()

    print(f"  Inserted : {inserted}")
    print(f"  Skipped  : {skipped} (already exist)")
    print(f"  Total    : {inserted + skipped} locations")
    print("=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
