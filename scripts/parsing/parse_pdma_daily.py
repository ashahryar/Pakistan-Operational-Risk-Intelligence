import json
import re
from pathlib import Path
from datetime import datetime

import pdfplumber
RAW_FOLDER = Path("data/raw/pdma/reports/daily_reports")
OUTPUT_FOLDER = Path("data/parsed/pdma/daily")

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

def extract_date(text):

    patterns = [

        r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,\s+\d{4})",

        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})",

        r"([A-Za-z]+\s+\d{1,2},\s+\d{4})"

    ]

    for pattern in patterns:

        match = re.search(pattern, text)

        if match:

            return match.group(1)

    return None

def extract_time(text):

    match = re.search(r"TIME[:\s]+(\d{3,4})", text)

    if match:

        return match.group(1)

    return None

def extract_forecast(text):

    start = text.find("WEATHER FORECAST")

    if start == -1:

        return ""

    forecast = text[start:start + 1200]

    return " ".join(forecast.split())

def extract_temperature(text):

    temps = re.findall(

        r"([A-Za-z ]+)=\s*(\d+)\s*°?C",

        text

    )

    data = {}

    for city, temp in temps:

        data[city.strip()] = int(temp)

    return data

def extract_rainfall(text):

    rain = re.findall(

        r"([A-Za-z ()]+)=\s*(\d+)",

        text

    )

    output = {}

    for city, value in rain:

        output[city.strip()] = float(value)

    return output

def extract_dams(text):

    dams = []

    pattern = re.compile(

        r"(Tarbela Dam|Mangla Dam|Bhakra Dam|Pong Dam|Thein Dam).*?(Normal|Low|Medium|High)",

        re.DOTALL

    )

    for match in pattern.finditer(text):

        dams.append({

            "dam": match.group(1),

            "status": match.group(2)

        })

    return dams

def parse_pdf(pdf_path):

    text = ""

    with pdfplumber.open(pdf_path) as pdf:

        for page in pdf.pages:

            page_text = page.extract_text()

            if page_text:

                text += page_text + "\n"

    data = {

        "pdf_name": pdf_path.name,

        "report_date": extract_date(text),

        "report_time": extract_time(text),

        "forecast": extract_forecast(text),

        "temperature": extract_temperature(text),

        "rainfall": extract_rainfall(text),

        "dams": extract_dams(text),

        "created_at": datetime.now().isoformat()

    }

    return data

def main():

    total = 0

    for year_folder in RAW_FOLDER.iterdir():

        pdf_folder = year_folder / "pdfs"

        if not pdf_folder.exists():

            continue

        output_year = OUTPUT_FOLDER / year_folder.name

        output_year.mkdir(parents=True, exist_ok=True)

        for pdf in pdf_folder.glob("*.pdf"):

            print(f"Parsing {pdf.name}")

            data = parse_pdf(pdf)

            output = output_year / f"{pdf.stem}.json"

            with open(output, "w", encoding="utf-8") as f:

                json.dump(data, f, indent=4)

            total += 1

    print(f"\nParsed {total} PDFs")

if __name__ == "__main__":
    main()