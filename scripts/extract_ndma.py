import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

URL = "https://www.ndma.gov.pk/advisories"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(URL, headers=HEADERS)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

cards = soup.find_all("a", class_="adv-card")

print(f"Found {len(cards)} advisories")

save_folder = "data/raw/ndma"
pdf_folder = os.path.join(save_folder, "pdfs")

os.makedirs(pdf_folder, exist_ok=True)

records = []

for card in cards:

    pdf_url = urljoin(URL, card.get("href"))

    title = card.find("p", class_="adv-card__title").get_text(strip=True)

    date = card.find("p", class_="adv-card__date").get_text(" ", strip=True)

    # Remove calendar icon text if present
    date = date.replace("calendar3", "").strip()

    filename = pdf_url.split("/")[-1]

    local_path = os.path.join(pdf_folder, filename)

    # Download PDF only if it doesn't already exist
    if not os.path.exists(local_path):

        pdf = requests.get(pdf_url, headers=HEADERS)

        if pdf.status_code == 200:

            with open(local_path, "wb") as f:
                f.write(pdf.content)

    records.append({
        "title": title,
        "date": date,
        "pdf_url": pdf_url,
        "local_file": local_path
    })

json_path = os.path.join(save_folder, "advisories.json")

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4, ensure_ascii=False)

print(f"\n✅ Metadata saved to {json_path}")
print(f"✅ PDFs downloaded in {pdf_folder}")
print(f"✅ Total advisories: {len(records)}")