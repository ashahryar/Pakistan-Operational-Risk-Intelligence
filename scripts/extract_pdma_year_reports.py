from playwright.sync_api import sync_playwright

url = "https://pdma.punjab.gov.pk/rainfall-reports"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    page = browser.new_page()

    page.goto(url, wait_until="networkidle")

    print(page.title())

    print(page.content()[:500])

    browser.close()