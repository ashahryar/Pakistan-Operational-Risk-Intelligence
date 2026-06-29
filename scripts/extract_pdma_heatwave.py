import os
import json
import requests
from bs4 import BeautifulSoup

URL = "https://pdma.punjab.gov.pk/heatwave-advisory"

SAVE_FOLDER = "data/raw/pdma/heatwave"
PDF_FOLDER = os.path.join(SAVE_FOLDER, "pdfs")

os.makedirs(PDF_FOLDER, exist_ok=True)

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(URL, headers=headers)
soup = BeautifulSoup(response.text, "html.parser")

cards = soup.find_all("div", class_="views-row")

records = []

print(f"Found {len(cards)} Heatwave Advisories\n")

for card in cards:

    a = card.find("a", href=True)

    if not a:
        continue

    pdf_url = a["href"]

    if pdf_url.startswith("/"):
        pdf_url = "https://pdma.punjab.gov.pk" + pdf_url

    title = card.find("div", class_="news-title-wrap").get_text(strip=True)

    date = card.find("time").get_text(strip=True)

    filename = pdf_url.split("/")[-1]

    local_path = os.path.join(PDF_FOLDER, filename)

    pdf = requests.get(pdf_url, headers=headers)

    with open(local_path, "wb") as f:
        f.write(pdf.content)

    records.append({
        "title": title,
        "date": date,
        "category": "Heatwave",
        "pdf_url": pdf_url,
        "local_file": local_path
    })

json_path = os.path.join(SAVE_FOLDER, "metadata.json")

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4, ensure_ascii=False)

print("Done")
print(f"Saved {len(records)} advisories")