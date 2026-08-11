from urllib.parse import urljoin
from bs4 import BeautifulSoup


def extract_pdf_links(
    soup: BeautifulSoup,
    page_url: str,
):
    """
    Extract report links (PDF + JPG + JPEG + PNG).
    """

    reports = []
    seen = set()

    VALID_EXTENSIONS = (
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
    )

    for a in soup.select("a[href]"):

        href = a.get("href", "").strip()
        print("FOUND:", href)

        href_lower = href.lower()

        from urllib.parse import urlparse

        parsed = urlparse(href_lower)

        path = parsed.path

        VALID_EXTENSIONS = (
            ".pdf",
            ".jpg",
            ".jpeg",
            ".png",
        )

        if not any(path.endswith(ext) for ext in VALID_EXTENSIONS):
            continue

        if href.startswith("http"):
            report_url = href
        else:
            report_url = urljoin(page_url, href)

        if report_url in seen:
            continue

        seen.add(report_url)

        title = a.get_text(" ", strip=True)

        if not title:
            title = report_url.split("/")[-1]

        reports.append(
            {
                "title": title,
                "url": report_url,
            }
        )

    return reports