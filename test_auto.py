from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://example.com")
    print(f"タイトル: {page.title()}")
    browser.close()
    print("テスト成功！")
