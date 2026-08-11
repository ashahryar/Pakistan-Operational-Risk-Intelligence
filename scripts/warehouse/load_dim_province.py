import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from config.database import engine


# ==========================================================
# Province Coordinates
# ==========================================================

PROVINCES = {

    "Punjab": {
        "country": "Pakistan",
        "latitude": 31.1704,
        "longitude": 72.7097
    },

    "Sindh": {
        "country": "Pakistan",
        "latitude": 25.8943,
        "longitude": 68.5247
    },

    "KP": {
        "country": "Pakistan",
        "latitude": 34.9526,
        "longitude": 72.3311
    },

    "Balochistan": {
        "country": "Pakistan",
        "latitude": 28.4907,
        "longitude": 65.0958
    },

    "GB": {
        "country": "Pakistan",
        "latitude": 35.8026,
        "longitude": 74.9832
    },

    "AJK": {
        "country": "Pakistan",
        "latitude": 33.9259,
        "longitude": 73.7810
    },

    "ICT": {
        "country": "Pakistan",
        "latitude": 33.6844,
        "longitude": 73.0479
    }

}


# ==========================================================
# Load Province Dimension
# ==========================================================

def load_dim_province():

    with engine.begin() as conn:

        conn.execute(text("DELETE FROM dim_province"))

        for province, info in PROVINCES.items():

            conn.execute(
                text(
                    """
                    INSERT INTO dim_province(

                        province_name,
                        country,
                        latitude,
                        longitude

                    )

                    VALUES(

                        :province_name,
                        :country,
                        :latitude,
                        :longitude

                    )
                    """
                ),
                {
                    "province_name": province,
                    "country": info["country"],
                    "latitude": info["latitude"],
                    "longitude": info["longitude"],
                },
            )

    print("=" * 60)
    print("DIM_PROVINCE LOADED")
    print(f"{len(PROVINCES)} provinces inserted")
    print("=" * 60)


# ==========================================================
# MAIN
# ==========================================================

def main():

    load_dim_province()


if __name__ == "__main__":
    main()