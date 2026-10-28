import csv
import getpass
import sys
from util.Login_face import login_face
from util.scrape import scrape_comments
from selenium import webdriver
from selenium.webdriver.chrome.options import Options



FIELDNAMES = [
    "inputUrl",
    "postTitle",
    "profileId",
    "profileName",
    "profilePicture",
    "text",
    "likesCount",
    "threadingDepth",
    "commentUrl",
    "timestamp",
    "pageAdLibrary/id",
    "pageAdLibrary/is_business_page_active",
]


def build_driver(headless: bool = False, debugger_address: str = None):
    options = Options()

    if debugger_address:
        options.debugger_address = debugger_address
        driver = webdriver.Chrome(options=options)
        return driver


    options.add_argument("--disable-notifications")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver

def save_to_csv(rows, filename="facebook_comments.csv"):
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved {len(rows)} comments to {filename}")


def main():
    print("=== Facebook Comment Scraper ===\n")
    print(
        "Two ways to run this:\n"
        "  1) Attach to a Chrome window you already logged into by hand\n"
        "     (recommended — avoids repeated automated logins that get\n"
        "     accounts flagged/checkpointed). See README.md setup steps.\n"
        "  2) Launch a fresh browser and log in with credentials here.\n"
    )
    use_attach = input("Attach to an already-open, logged-in Chrome? (y/n): ").strip().lower().startswith("y")

    email = password = None
    debugger_address = None

    if use_attach:
        debugger_address = input(
            "Debugger address (default 127.0.0.1:9222, press Enter to accept): "
        ).strip() or "127.0.0.1:9222"
    else:
        email = input("Facebook email or phone: ").strip()
        password = getpass.getpass("Facebook password (hidden): ")

    post_url = input("Post URL to scrape: ").strip()
    content_type = input("Content type (post/reel, Enter to detect from URL): ").strip().lower()
    while content_type not in ("", "post", "reel"):
        content_type = input("Please enter post or reel: ").strip().lower()
    try:
        max_comments = int(input("Max comments to collect (e.g. 75): ").strip())
    except ValueError:
        max_comments = 75

    driver = build_driver(headless=False, debugger_address=debugger_address)
    try:
        if not use_attach:
            login_face(driver, email, password)
        else:
            print(
                "\nAttached to existing Chrome. Make sure that window is "
                "already logged into Facebook before continuing.\n"
            )

        rows = scrape_comments(driver, post_url, max_comments, content_type or None)

        if not rows:
            print(
                "\nNo comments were extracted. This usually means Facebook's "
                "page structure has changed and the selectors in this script "
                "need updating, or the login/checkpoint step didn't fully "
                "complete."
            )
        else:
            save_to_csv(rows)
    finally:
        if not use_attach:
            driver.quit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nCancelled.")
