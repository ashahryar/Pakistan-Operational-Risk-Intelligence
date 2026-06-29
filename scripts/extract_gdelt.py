import os
import json
import requests
from datetime import datetime

SAVE_DIR = "data/raw/gdelt"
os.makedirs(SAVE_DIR, exist_ok=True)

url = (
    "https://api.gdeltproject.org/api/v2/doc/doc"
    "?query=Pakistan"
    "&mode=ArtList"
    "&maxrecords=100"
    "&format=json"
)

print("Fetching GDELT data...")

response = requests.get(url, timeout=30)
response.raise_for_status()

data = response.json()

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

file_path = os.path.join(
    SAVE_DIR,
    f"gdelt_{timestamp}.json"
)

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4)

print(f"Saved: {file_path}")

articles = data.get("articles", [])

print(f"Articles fetched: {len(articles)}")

if articles:
    print("\nSample Article:")
    print(articles[0]["title"])