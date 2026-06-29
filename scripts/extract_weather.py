import os
import json
import requests
from datetime import datetime

cities = [
    {"name": "karachi", "lat": 24.8607, "lon": 67.0011},
    {"name": "lahore", "lat": 31.5497, "lon": 74.3436},
    {"name": "islamabad", "lat": 33.6844, "lon": 73.0479},
    {"name": "peshawar", "lat": 34.0151, "lon": 71.5249},
]

save_dir = "data/raw/weather"
os.makedirs(save_dir, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

for city in cities:

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={city['lat']}"
        f"&longitude={city['lon']}"
        f"&current=temperature_2m,relative_humidity_2m,rain,wind_speed_10m,pressure_msl"
        f"&hourly=temperature_2m,relative_humidity_2m,rain,wind_speed_10m"
        f"&forecast_days=7"
    )

    response = requests.get(url)
    response.raise_for_status()

    data = response.json()

    file_path = os.path.join(
        save_dir,
        f"{city['name']}_weather_{timestamp}.json"
    )

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    print(f"✅ Saved: {file_path}")

print("\n🎉 Weather data for all cities saved successfully.")