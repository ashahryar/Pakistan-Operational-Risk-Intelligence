import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load .env file
load_dotenv()

TOKEN = os.getenv("WAQI_API_TOKEN")

if not TOKEN:
    raise ValueError("WAQI_API_TOKEN not found in .env file")

# Pakistan Cities
cities = [
    "karachi",
    "lahore",
    "islamabad",
    "rawalpindi",
    "peshawar"
]

save_dir = "data/raw/aqi"
os.makedirs(save_dir, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

for city in cities:

    url = f"https://api.waqi.info/feed/{city}/?token={TOKEN}"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Check API response
        if data["status"] != "ok":
            print(f"❌ No data found for {city}")
            continue

        file_path = os.path.join(
            save_dir,
            f"{city}_aqi_{timestamp}.json"
        )

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

        print(f"✅ Saved: {file_path}")

    except Exception as e:
        print(f"❌ Error fetching {city}: {e}")

print("\n🎉 AQI data for all cities saved successfully.")