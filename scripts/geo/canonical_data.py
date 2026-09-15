"""
scripts/geo/canonical_data.py

Phase 1 / Task 10 (ADR-0001) -- the canonical province and district
lists for the geographic foundation.

NOT an authoritative government boundary dataset. No HDX/OCHA COD-AB,
GADM, or P-code file exists anywhere in this repository (confirmed by
a repo-wide search during Task 10 planning), and none is downloaded
here -- per the approved plan, Task 10 reconciles the two datasets
that were ALREADY present and locally authored in this repo:

  1. scripts/database/create_geo_tables.py's `LOCATIONS` seed list
     (Punjab districts, rivers, PMD cities, provinces -- ~95 rows)
  2. data/master/district_master.csv (38 districts, national coverage,
     lat/lon) -- previously unreferenced by any code in the repo

No new district or province is invented; every entry here is traced
to one (or both) of those two files, tagged via its `source` field.
Stable IDs are this repo's own surrogate keys -- no real P-codes exist
locally to preserve, so `pcode` is intentionally left unset/None
everywhere; adopting real P-codes is documented future work, not
attempted here.

This module has NO database import and NO I/O -- it is a pure data
structure, directly unit-tested by tests/geo/test_canonical_data.py.
"""

from __future__ import annotations

# ==========================================================
# PROVINCES / REGIONS (level 1)
# ==========================================================
# Canonical name + every real spelling/abbreviation variant actually
# seen in this repo's own code or live database data (not invented):
#   - geo_locations' own "PROVINCES" seed block already encodes
#     several of these as bidirectional (name, name_alt) pairs.
#   - Live pdma/ndma_casualties|damage|rescue.province: abbreviated
#     set (AJ&K, Balochistan, GB, ICT, KP, Punjab, Sindh).
#   - Live pmd_weekly_outlook.regions / pmd_weather_alerts.regions:
#     full-name set (AJK, Balochistan, Gilgit Baltistan, Islamabad,
#     Khyber Pakhtunkhwa, Punjab, Sindh) -- note "AJK" here, not
#     "AJ&K", and "Islamabad" not "ICT".

PROVINCES = [
    {
        "name": "Punjab",
        "aliases": [],
        "source": "geo_locations",
    },
    {
        "name": "Sindh",
        "aliases": [],
        "source": "geo_locations",
    },
    {
        "name": "Khyber Pakhtunkhwa",
        "aliases": ["KP"],
        "source": "geo_locations",
    },
    {
        "name": "Balochistan",
        "aliases": [],
        "source": "geo_locations",
    },
    {
        "name": "Gilgit-Baltistan",
        "aliases": ["GB", "Gilgit Baltistan"],
        "source": "geo_locations",
    },
    {
        "name": "Azad Jammu & Kashmir",
        "aliases": ["AJK", "AJ&K", "Azad Kashmir"],
        "source": "geo_locations",
    },
    {
        "name": "Islamabad Capital Territory",
        "aliases": ["ICT", "Islamabad"],
        "source": "geo_locations",
    },
]

# ==========================================================
# DISTRICTS (level 2)
# ==========================================================
# Union of geo_locations' 41-row "PUNJAB DISTRICTS" seed block (two of
# those rows -- Muzaffarabad, Rawalakot -- are actually tagged AJK
# within that same block, a pre-existing quirk in the source data, not
# introduced here) and district_master.csv's 38-row national list.
# 11 names overlap between the two sources (merged below, source
# tagged "geo_locations+district_master_csv").
#
# KNOWN CAVEAT, carried through as-is (not "corrected" by original
# administrative research, which would mean inventing authoritative
# knowledge this task is told not to fabricate): four entries in
# geo_locations' own seed data are not actually districts --
#   - Mangla     -- a reservoir/dam town in Mirpur (AJK) district
#   - Fort Munro  -- a hill station within Dera Ghazi Khan district
#   - Kamra      -- an air-base town within Attock district
#   - Joharabad   -- a town within Khushab district
# These are pre-existing inaccuracies already in the repo's own data,
# not introduced by Task 10. Flagged via `caveat` below and in
# docs/geo/GEOGRAPHIC_FOUNDATION.md.

DISTRICTS = [
    # ---- Punjab (40, from geo_locations' Punjab-tagged rows) ----
    {"name": "Attock", "province": "Punjab", "aliases": [], "lat": 33.7667, "lon": 72.3667, "source": "geo_locations"},
    {"name": "Bahawalnagar", "province": "Punjab", "aliases": [], "lat": 29.9956, "lon": 73.2536, "source": "geo_locations"},
    {"name": "Bahawalpur", "province": "Punjab", "aliases": [], "lat": 29.3956, "lon": 71.6722, "source": "geo_locations+district_master_csv"},
    {"name": "Bhakkar", "province": "Punjab", "aliases": [], "lat": 31.6278, "lon": 71.0644, "source": "geo_locations"},
    {"name": "Chakwal", "province": "Punjab", "aliases": [], "lat": 32.9328, "lon": 72.8528, "source": "geo_locations"},
    {"name": "Chiniot", "province": "Punjab", "aliases": [], "lat": 31.7200, "lon": 72.9800, "source": "geo_locations"},
    {"name": "Dera Ghazi Khan", "province": "Punjab", "aliases": ["D.G. Khan", "DG Khan", "D G Khan"], "lat": 30.0500, "lon": 70.6333, "source": "geo_locations+district_master_csv"},
    {"name": "Faisalabad", "province": "Punjab", "aliases": [], "lat": 31.4180, "lon": 73.0790, "source": "geo_locations+district_master_csv"},
    {"name": "Fort Munro", "province": "Punjab", "aliases": [], "lat": 29.8667, "lon": 70.1833, "source": "geo_locations", "caveat": "not a real district -- a hill station within Dera Ghazi Khan district"},
    {"name": "Gujranwala", "province": "Punjab", "aliases": [], "lat": 32.1617, "lon": 74.1883, "source": "geo_locations+district_master_csv"},
    {"name": "Gujrat", "province": "Punjab", "aliases": [], "lat": 32.5736, "lon": 74.0789, "source": "geo_locations"},
    {"name": "Hafizabad", "province": "Punjab", "aliases": [], "lat": 32.0711, "lon": 73.6883, "source": "geo_locations"},
    {"name": "Jhang", "province": "Punjab", "aliases": [], "lat": 31.2681, "lon": 72.3181, "source": "geo_locations"},
    {"name": "Jhelum", "province": "Punjab", "aliases": [], "lat": 32.9361, "lon": 73.7261, "source": "geo_locations"},
    {"name": "Joharabad", "province": "Punjab", "aliases": [], "lat": 32.2667, "lon": 72.6333, "source": "geo_locations", "caveat": "not a real district -- a town within Khushab district"},
    {"name": "Kamra", "province": "Punjab", "aliases": [], "lat": 33.8667, "lon": 72.4000, "source": "geo_locations", "caveat": "not a real district -- an air-base town within Attock district"},
    {"name": "Kasur", "province": "Punjab", "aliases": [], "lat": 31.1167, "lon": 74.4500, "source": "geo_locations"},
    {"name": "Khanewal", "province": "Punjab", "aliases": [], "lat": 30.3000, "lon": 71.9333, "source": "geo_locations"},
    {"name": "Khanpur", "province": "Punjab", "aliases": [], "lat": 28.6472, "lon": 70.6556, "source": "geo_locations"},
    {"name": "Khushab", "province": "Punjab", "aliases": [], "lat": 32.2972, "lon": 72.3528, "source": "geo_locations"},
    {"name": "Kot Addu", "province": "Punjab", "aliases": [], "lat": 30.4667, "lon": 70.9667, "source": "geo_locations"},
    {"name": "Lahore", "province": "Punjab", "aliases": [], "lat": 31.5497, "lon": 74.3436, "source": "geo_locations+district_master_csv"},
    {"name": "Layyah", "province": "Punjab", "aliases": [], "lat": 30.9597, "lon": 70.9397, "source": "geo_locations"},
    {"name": "Mandi Bahauddin", "province": "Punjab", "aliases": ["Mandi Bahaddin", "Mandi Bahuddin"], "lat": 32.5864, "lon": 73.4917, "source": "geo_locations"},
    {"name": "Mangla", "province": "Punjab", "aliases": [], "lat": 33.1333, "lon": 73.6500, "source": "geo_locations", "caveat": "not a real district -- a reservoir/dam town in Mirpur (AJK) district"},
    {"name": "Mianwali", "province": "Punjab", "aliases": [], "lat": 32.5853, "lon": 71.5436, "source": "geo_locations"},
    {"name": "Multan", "province": "Punjab", "aliases": [], "lat": 30.1978, "lon": 71.4711, "source": "geo_locations+district_master_csv"},
    {"name": "Murree", "province": "Punjab", "aliases": [], "lat": 33.9042, "lon": 73.3903, "source": "geo_locations"},
    {"name": "Narowal", "province": "Punjab", "aliases": [], "lat": 32.1000, "lon": 74.8667, "source": "geo_locations"},
    {"name": "Noorpur Thal", "province": "Punjab", "aliases": ["Noor Pur Thal", "Noorpurthal"], "lat": 31.5833, "lon": 71.9000, "source": "geo_locations"},
    {"name": "Okara", "province": "Punjab", "aliases": [], "lat": 30.8100, "lon": 73.4500, "source": "geo_locations"},
    {"name": "Rahim Yar Khan", "province": "Punjab", "aliases": ["R.Y. Khan", "RY Khan"], "lat": 28.4202, "lon": 70.2952, "source": "geo_locations+district_master_csv"},
    {"name": "Rajanpur", "province": "Punjab", "aliases": [], "lat": 29.1044, "lon": 70.3297, "source": "geo_locations"},
    {"name": "Rawalpindi", "province": "Punjab", "aliases": [], "lat": 33.5651, "lon": 73.0169, "source": "geo_locations+district_master_csv"},
    {"name": "Sahiwal", "province": "Punjab", "aliases": [], "lat": 30.6706, "lon": 73.1064, "source": "geo_locations"},
    {"name": "Sargodha", "province": "Punjab", "aliases": [], "lat": 32.0836, "lon": 72.6711, "source": "geo_locations+district_master_csv"},
    {"name": "Sheikhupura", "province": "Punjab", "aliases": [], "lat": 31.7131, "lon": 73.9850, "source": "geo_locations"},
    {"name": "Sialkot", "province": "Punjab", "aliases": [], "lat": 32.4945, "lon": 74.5229, "source": "geo_locations+district_master_csv"},
    {"name": "Toba Tek Singh", "province": "Punjab", "aliases": [], "lat": 30.9667, "lon": 72.4833, "source": "geo_locations"},
    {"name": "Wazirabad", "province": "Punjab", "aliases": [], "lat": 32.4431, "lon": 74.1197, "source": "geo_locations"},

    # ---- Azad Jammu & Kashmir (3) ----
    {"name": "Muzaffarabad", "province": "Azad Jammu & Kashmir", "aliases": [], "lat": 34.3700, "lon": 73.4711, "source": "geo_locations+district_master_csv"},
    {"name": "Rawalakot", "province": "Azad Jammu & Kashmir", "aliases": [], "lat": 33.8578, "lon": 73.7614, "source": "geo_locations"},
    {"name": "Mirpur", "province": "Azad Jammu & Kashmir", "aliases": [], "lat": 33.1480, "lon": 73.7510, "source": "district_master_csv"},

    # ---- Sindh (10, from district_master.csv) ----
    {"name": "Karachi", "province": "Sindh", "aliases": [], "lat": 24.8607, "lon": 67.0011, "source": "district_master_csv"},
    {"name": "Hyderabad", "province": "Sindh", "aliases": [], "lat": 25.3960, "lon": 68.3578, "source": "district_master_csv"},
    {"name": "Sukkur", "province": "Sindh", "aliases": [], "lat": 27.7052, "lon": 68.8574, "source": "district_master_csv"},
    {"name": "Larkana", "province": "Sindh", "aliases": [], "lat": 27.5609, "lon": 68.2264, "source": "district_master_csv"},
    {"name": "Thatta", "province": "Sindh", "aliases": [], "lat": 24.7475, "lon": 67.9248, "source": "district_master_csv"},
    {"name": "Badin", "province": "Sindh", "aliases": [], "lat": 24.6560, "lon": 68.8370, "source": "district_master_csv"},
    {"name": "Mirpur Khas", "province": "Sindh", "aliases": [], "lat": 25.5269, "lon": 69.0126, "source": "district_master_csv"},
    {"name": "Nawabshah", "province": "Sindh", "aliases": [], "lat": 26.2442, "lon": 68.4100, "source": "district_master_csv"},
    {"name": "Khairpur", "province": "Sindh", "aliases": [], "lat": 27.5295, "lon": 68.7592, "source": "district_master_csv"},
    {"name": "Jacobabad", "province": "Sindh", "aliases": [], "lat": 28.2819, "lon": 68.4376, "source": "district_master_csv"},

    # ---- Islamabad Capital Territory (1) ----
    {"name": "Islamabad", "province": "Islamabad Capital Territory", "aliases": [], "lat": 33.6844, "lon": 73.0479, "source": "district_master_csv"},

    # ---- Khyber Pakhtunkhwa (8, from district_master.csv) ----
    {"name": "Peshawar", "province": "Khyber Pakhtunkhwa", "aliases": [], "lat": 34.0151, "lon": 71.5249, "source": "district_master_csv"},
    {"name": "Mardan", "province": "Khyber Pakhtunkhwa", "aliases": [], "lat": 34.1989, "lon": 72.0401, "source": "district_master_csv"},
    {"name": "Swat", "province": "Khyber Pakhtunkhwa", "aliases": [], "lat": 35.2227, "lon": 72.4258, "source": "district_master_csv"},
    {"name": "Abbottabad", "province": "Khyber Pakhtunkhwa", "aliases": [], "lat": 34.1688, "lon": 73.2215, "source": "district_master_csv"},
    {"name": "Mansehra", "province": "Khyber Pakhtunkhwa", "aliases": [], "lat": 34.3302, "lon": 73.1968, "source": "district_master_csv"},
    {"name": "Kohat", "province": "Khyber Pakhtunkhwa", "aliases": [], "lat": 33.5889, "lon": 71.4429, "source": "district_master_csv"},
    {"name": "Bannu", "province": "Khyber Pakhtunkhwa", "aliases": [], "lat": 32.9854, "lon": 70.6027, "source": "district_master_csv"},
    {"name": "Dera Ismail Khan", "province": "Khyber Pakhtunkhwa", "aliases": ["D.I. Khan", "DI Khan"], "lat": 31.8315, "lon": 70.9017, "source": "district_master_csv"},

    # ---- Balochistan (5, from district_master.csv) ----
    {"name": "Quetta", "province": "Balochistan", "aliases": [], "lat": 30.1798, "lon": 66.9750, "source": "district_master_csv"},
    {"name": "Gwadar", "province": "Balochistan", "aliases": [], "lat": 25.1216, "lon": 62.3254, "source": "district_master_csv"},
    {"name": "Khuzdar", "province": "Balochistan", "aliases": [], "lat": 27.8126, "lon": 66.6100, "source": "district_master_csv"},
    {"name": "Turbat", "province": "Balochistan", "aliases": [], "lat": 26.0023, "lon": 63.0440, "source": "district_master_csv"},
    {"name": "Zhob", "province": "Balochistan", "aliases": [], "lat": 31.3408, "lon": 69.4493, "source": "district_master_csv"},

    # ---- Gilgit-Baltistan (2, from district_master.csv) ----
    {"name": "Gilgit", "province": "Gilgit-Baltistan", "aliases": [], "lat": 35.9208, "lon": 74.3140, "source": "district_master_csv"},
    {"name": "Skardu", "province": "Gilgit-Baltistan", "aliases": [], "lat": 35.2971, "lon": 75.6337, "source": "district_master_csv"},
]
