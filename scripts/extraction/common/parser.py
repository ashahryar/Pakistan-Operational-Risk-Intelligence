"""
parser.py

Common HTML parsing helpers.
"""

from urllib.parse import urljoin

from bs4 import BeautifulSoup


def extract_pdf_links(
    soup: BeautifulSoup,
    page_url: str,
):
    """
    Extract unique PDF links.
    """

    pdfs = []
    seen = set()

    for a in soup.select("a[href]"):

        href = a.get("href", "").strip()

        if ".pdf" not in href.lower():
            continue

        pdf_url = urljoin(page_url, href)

        if pdf_url in seen:
            continue

        seen.add(pdf_url)

        title = a.get_text(" ", strip=True)

        if not title:
            title = pdf_url.split("/")[-1]

        pdfs.append(
            {
                "title": title,
                "url": pdf_url,
            }
        )

    return pdfs