from bs4 import BeautifulSoup


def extract_forecast_text(soup: BeautifulSoup):

    blocks = []

    for div in soup.select("div.well h5"):

        text = div.get_text(" ", strip=True)

        if text:
            blocks.append(text)

    return "\n".join(blocks)


def extract_tables(soup: BeautifulSoup):

    tables = []

    for table in soup.select("table"):

        headers = []

        head = table.find("tr")

        if not head:
            continue

        for th in head.find_all(["th", "td"]):
            headers.append(th.get_text(strip=True))

        rows = []

        for tr in table.find_all("tr")[1:]:

            cols = [
                td.get_text(" ", strip=True)
                for td in tr.find_all("td")
            ]

            if cols:
                rows.append(cols)

        if rows:
            tables.append(
                {
                    "headers": headers,
                    "rows": rows,
                }
            )

    return tables


