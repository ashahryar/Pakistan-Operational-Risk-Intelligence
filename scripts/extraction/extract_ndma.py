import argparse
from datetime import datetime
from typing import Dict,List

from bs4 import BeautifulSoup

from common.downloader import download_file
from common.fetcher import HTTPClient
from common.filesystem import (
    get_pdf_directory,
    get_report_directory,
)
from common.logger import setup_logger
from common.metadata import (
    get_downloaded_files,
    load_metadata,
    save_metadata,
)
from urllib.parse import urlparse
from pathlib import Path
from common.parser import extract_pdf_links

logger = setup_logger("ndma")
client = HTTPClient()
# ==========================================================
# CONFIGURATION
# ==========================================================
MAX_EMPTY_PAGES = 1
REPORTS = {

    "sitreps": {
        "url": "https://ndma.gov.pk/sitreps?cat_id=3&page={}",
        "folder": "sitreps",
    },

    "advisories": {
        "url": "https://ndma.gov.pk/advisories?page={}",
        "folder": "advisories",
    },

    "guidelines": {
        "url": "https://ndma.gov.pk/guidelines?page={}",
        "folder": "guidelines",
    },
}

# ==========================================================
# CORE SCRAPE LOGIC FOR ONE REPORT/YEAR
# ==========================================================

def scrape_report(report_key: str, config: Dict[str, str]) -> int:
    """Scrape all pages for a given report type and year."""

    folder = get_report_directory(
    "ndma",
    config["folder"],
    "all"
)

    pdf_folder = get_pdf_directory(
    "ndma",
    config["folder"],
    "all"
)
    metadata = load_metadata(folder)

    downloaded_files = get_downloaded_files(metadata)

    page = 0
    empty_pages = 0
    downloaded_count = 0

    while True:

        page_url = config["url"].format(page)

        logger.info("%s | Page %s", report_key, "all", page)

        response = client.get(page_url)

        if response is None:
            break

        soup = BeautifulSoup(response.text, "html.parser")

        pdf_links = extract_pdf_links(soup, page_url)

        print(f"\nChecking Page : {page}")
        print(f"Found {len(pdf_links)} PDFs")

        if len(pdf_links) == 0:

            empty_pages += 1

            if empty_pages >= MAX_EMPTY_PAGES:

                print("Finished This Report.")

                break

            page += 1

            continue

        empty_pages = 0

        print("ENTERING DOWNLOAD LOOP")

        for pdf in pdf_links:

            print(pdf["url"])

            filename = Path(urlparse(pdf["url"]).path).name

            if filename in downloaded_files:

                print(f"Already Exists : {filename}")

                continue

            output = pdf_folder / filename

            print(f"Downloading : {filename}")

            success = download_file(pdf["url"], output)

            if success:

                downloaded_files.add(filename)

                downloaded_count += 1

                metadata.append({

                    "title": pdf["title"],
                    "filename": filename,
                    "category": report_key,
                    "page": page,
                    "url": pdf["url"],
                    "download_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                })

                logger.info(f"Downloaded {filename}")

            else:

                logger.error(f"Failed {filename}")

        save_metadata(folder, metadata)

        page += 1

    return downloaded_count


# ==========================================================
# MAIN
# ==========================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="NDMA Pakistan reports scraper")
    parser.add_argument(
        "report",
        choices=list(REPORTS.keys()) + ["all"],
        help="sitreps | advisories | guidelines | all",
    )
    args = parser.parse_args()

    report_list = list(REPORTS.keys()) if args.report == "all" else [args.report]

    total_downloaded = 0

    for report_key in report_list:

        print("\n" + "=" * 70)
        print(f"Starting Report : {report_key.upper()}")
        print("=" * 70)

        config = REPORTS[report_key]

        total_downloaded += scrape_report(
            report_key,
            config
        )

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("Reports        :", len(report_list))
    print("PDFs Downloaded:", total_downloaded)
    print("Completed Successfully")
    print("=" * 70)


if __name__ == "__main__":
    main()