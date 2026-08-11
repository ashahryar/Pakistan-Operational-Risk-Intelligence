import requests
from bs4 import BeautifulSoup


URL = "https://www.ndma.gov.pk/"


def check_new_pdf():

    response = requests.get(URL, timeout=30)

    soup = BeautifulSoup(

        response.text,

        "html.parser"

    )

    pdfs = []

    for a in soup.find_all("a", href=True):

        href = a["href"]

        if ".pdf" in href.lower():

            pdfs.append(href)

    print(f"Found {len(pdfs)} PDFs")

    return pdfs