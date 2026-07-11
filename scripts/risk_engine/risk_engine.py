"""
Operational Risk Engine

Reads

PMD
PDMA
NDMA

Calculates

Risk Score
Risk Level
Recommendation

Stores

operational_risk
"""

import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine


# ==========================================================
# RISK FUNCTIONS
# ==========================================================

def rainfall_score(rainfall):

    if rainfall is None:
        return 0

    if rainfall >= 100:
        return 35

    if rainfall >= 50:
        return 25

    if rainfall >= 20:
        return 15

    if rainfall > 0:
        return 5

    return 0


def weather_score(alert):

    if not alert:
        return 0

    alert = alert.lower()

    score = 0

    if "heavy" in alert:
        score += 30

    if "rain" in alert:
        score += 15

    if "storm" in alert:
        score += 20

    if "thunder" in alert:
        score += 15

    if "heat" in alert:
        score += 15

    return score


def casualty_score(value):

    if value is None:
        return 0

    if value >= 20:
        return 30

    if value >= 10:
        return 20

    if value >= 5:
        return 10

    if value > 0:
        return 5

    return 0


def damage_score(value):

    if value is None:
        return 0

    if value >= 20:
        return 20

    if value >= 10:
        return 15

    if value >= 5:
        return 10

    if value > 0:
        return 5

    return 0


def risk_level(score):

    if score >= 81:
        return "CRITICAL"

    if score >= 61:
        return "HIGH"

    if score >= 31:
        return "MEDIUM"

    return "LOW"


def recommendation(level):

    mapping = {

        "LOW":
            "Normal Operations",

        "MEDIUM":
            "Monitor Conditions",

        "HIGH":
            "Delay Field Operations",

        "CRITICAL":
            "Avoid Dispatch"

    }

    return mapping[level]


# ==========================================================
# MAIN ENGINE
# ==========================================================

def main():

    with engine.begin() as conn:

        # Clean previous results

        conn.execute(text("TRUNCATE operational_risk RESTART IDENTITY"))

        # Weather alert

        alert = conn.execute(text("""

            SELECT forecast

            FROM pmd_weather_alerts

            ORDER BY scraped_at DESC

            LIMIT 1

        """)).scalar()

        weather_points = weather_score(alert)

        # Cities

        cities = conn.execute(text("""

            SELECT

                city,
                province

            FROM pmd_daily_forecast

        """)).fetchall()

        total = 0

        for city in cities:

            rainfall = conn.execute(text("""

                SELECT MAX(rainfall_mm)

                FROM pdma_rainfall_readings

            """)).scalar()

            casualties = conn.execute(text("""

                SELECT COALESCE(SUM(deaths),0)

                FROM ndma_casualties

            """)).scalar()

            damages = conn.execute(text("""

                SELECT COUNT(*)

                FROM ndma_damage

            """)).scalar()

            score = (

                rainfall_score(rainfall)
                + weather_points
                + casualty_score(casualties)
                + damage_score(damages)

            )

            if score > 100:
                score = 100

            level = risk_level(score)

            conn.execute(text("""

                INSERT INTO operational_risk(

                    city,
                    province,
                    rainfall_mm,
                    weather_alert,
                    casualties,
                    damage_reports,
                    risk_score,
                    risk_level,
                    recommendation

                )

                VALUES(

                    :city,
                    :province,
                    :rainfall,
                    :weather,
                    :casualties,
                    :damage,
                    :score,
                    :level,
                    :recommendation

                )

            """),{

                "city": city.city,

                "province": city.province,

                "rainfall": rainfall,

                "weather": alert,

                "casualties": casualties,

                "damage": damages,

                "score": score,

                "level": level,

                "recommendation": recommendation(level)

            })

            total += 1

    print("=" * 60)
    print("Operational Risk Engine Completed")
    print("=" * 60)
    print(f"Cities Processed : {total}")
    print("=" * 60)


if __name__ == "__main__":
    main()