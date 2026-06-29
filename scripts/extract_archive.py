import os
import json
import requests
from bs4 import BeautifulSoup

URL = "https://www.ndma.gov.pk/sitreps"

response = requests.get(URL)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

cards = soup.find_all("a", class_="sr-card")

print(f"Found {len(cards)} Archive Reports")

save_folder = "data/raw/ndma/archive"
pdf_folder = os.path.join(save_folder, "pdfs")

os.makedirs(pdf_folder, exist_ok=True)

records = []

for card in cards:

    title = card.find("p", class_="sr-card__title").get_text(strip=True)
    date = card.find("p", class_="sr-card__date").get_text(strip=True)

    pdf_url = card["href"]

    if pdf_url.startswith("//"):
        pdf_url = "https:" + pdf_url
    elif pdf_url.startswith("/"):
        pdf_url = "https://www.ndma.gov.pk" + pdf_url

    filename = pdf_url.split("/")[-1]
    local_path = os.path.join(pdf_folder, filename)

    print(f"Downloading {filename}")

    pdf = requests.get(pdf_url)

    with open(local_path, "wb") as f:
        f.write(pdf.content)

    records.append({
        "title": title,
        "date": date,
        "pdf_url": pdf_url,
        "local_file": local_path
    })

json_path = os.path.join(save_folder, "metadata.json")

with open(json_path, "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4, ensure_ascii=False)

print("\n==============================")
print("✅ Archive Download Complete")
print(f"Reports : {len(records)}")
print(f"Metadata : {json_path}")
print(f"PDF Folder : {pdf_folder}")
print("==============================")