## Facebook Comment Scraper

A Selenium-based tool that logs into Facebook with a real account and exports
comments from a post or reel to a CSV file.

## Read this first

- **A real login is required.** Facebook shows guest accounts almost nothing noteworthy, so a real account is required.
- **Use a throwaway/burner account.** Automating Facebook login violates its Terms of Service, and the account you use can
  get temporarily locked or permanently disabled.
  So, it is best to use a fresh burner account every few sessions/days to avoid the corpo laws.
- **Facebook's page structure changes often.** The selectors in `util/scrape.py`
  are current as of testing but may stop working after a Facebook UI update.
  If that happens, see [Troubleshooting](#troubleshooting) below.

## Requirements

- Python 3.9+
- Google Chrome installed
- Selenium manages ChromeDriver automatically when creating the browser.
  The first run may need internet access to download a compatible driver.

## Setup

```bash
# 1. Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows

# 2. Install dependencies
pip install -r requirements.txt
```

### Setup (Windows)

1. Close all Chrome windows first.
2. Open Command Prompt and run (adjust the path to your Chrome install
   if different):
   ```
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\selenium\ChromeProfile"
   ```
3. In the Chrome window that opens, log into Facebook normally — solve
   any checkpoint/2FA as a human would, just this once.
4. Leave that window open, then in a separate terminal run:
   ```
   python main.py
   ```
5. When asked "Attach to an already-open, logged-in Chrome?", answer `y`
   and accept the default address (`127.0.0.1:9222`).

The script will now scrape using that already-logged-in session instead
of logging in itself. You can reuse the same Chrome window (same
`--user-data-dir` profile) across multiple runs without logging in again,
as long as you keep launching Chrome with the same command.

### Setup (macOS/Linux)

Replace the Chrome path:
```
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="$HOME/selenium-chrome-profile"   # macOS
google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/selenium-chrome-profile"   # Linux
```

## Alternative: fresh login each run

Answer `n` at the attach prompt to launch a fresh Chrome window and enter
your credentials. If Facebook requests verification, complete it in the
browser, then press Enter in the terminal.

## Posts and reels

After entering the URL, choose `post` or `reel`, or press Enter to detect the
type from the URL. For shortened links that cannot be recognized, choose `reel`
explicitly. Reel mode tries to open the comments panel. If prompted, open the
side comments panel manually and press Enter in the terminal.

Reel mode targets the side comments panel, including layouts using
`role="complementary"`, and scrolls its inner comments list. If automatic
detection fails:

1. Open the reel's comments panel in Chrome and press Enter when prompted.
2. If the panel still is not recognized, wait for the selection prompt,
   click a comment inside the side list, then press Enter in the terminal.
3. If the panel is replaced during scraping, select it again when prompted.

Some reels load only a few comments per batch. The scraper saves the current
batch before pressing a load-more control, then reads the next batch before
scrolling again. It stops after repeated attempts produce no new comments.

### Button languages

Load-more and reply controls are matched by text in **English, Urdu, and
Persian**, including `View more comments`, `مزید کمنٹس دیکھیں`, and
`نظرات بیشتر`. This is support for specific labels, not every possible
translation or Facebook layout. Other interface languages may require adding
their labels to `_is_load_more_label()` in `util/scrape.py`.

Automatic opening of the reel comments panel and switching to "All comments"
currently use English labels. Open the panel and select the desired sort
manually if your interface uses another language.

## Prompts and output

Depending on the login mode, you'll be prompted for:

| Prompt                        | Notes                                           |
|-------------------------------|-------------------------------------------------|
| Facebook email or phone       | The account you're logging in with              |
| Facebook password             | Entered hidden, never stored or logged          |
| Post URL to scrape            | Full URL of the Facebook post                   |
| Content type                  | `post`, `reel`, or Enter for URL detection      |
| Max comments to collect       | e.g. `75`                                       |

Output is written to `facebook_comments.csv` in this folder, with columns:

```
inputUrl, postTitle, profileId, profileName, profilePicture, text,
likesCount, threadingDepth, commentUrl, timestamp,
pageAdLibrary/id, pageAdLibrary/is_business_page_active
```

The last two columns are always left blank. That data comes from
Facebook's separate Ad Library API for business/advertiser Pages, not from
the comments themselves.

While it runs, you'll see progress lines like:

```
[progress] round 4: 27 unique comments collected so far
```

That count is real-time and cumulative, as the script now extracts
comments continuously as it scrolls, rather than only reading the page
once at the end. This matters because Facebook deletes comment elements
from the page's HTML once they scroll out of view.

**On very large posts ("11K comments" style counts):** don't expect to
collect anywhere near the total. Facebook throttles how fast more
comments load, this script waits between actions on purpose to avoid
looking like a bot, and many older/deeply nested replies never load into
the page at all without much more aggressive and risky automation.
Realistic output for one run is dozens to a few hundred comments.

## How it works

1. Attaches to your logged-in Chrome session or opens Chrome for a fresh login.
2. Navigates to the post or reel URL and switches comment sorting to "All comments"
   if that option is available.
3. For reels, opens or identifies the side comments panel. Saves each batch,
   clicks supported load-more controls, and scrolls until it collects the
   requested number of comments (or stops finding new ones).
4. Parses each comment block for author, text, likes, and timestamp.
5. Writes everything to a CSV file.

## Troubleshooting

**Login fails with a timeout / can't find the email field**
Facebook likely served a different page than expected (a cookie-consent
wall, a regional login variant, or a bot-detection page). The script saves
a screenshot (`login_page_not_found.png`) and prints the URL/title it
actually landed on — check that file to see what happened, then update the
selectors in `login_face()` in `util/Login_face.py` to match.

**Login succeeds but then asks for extra verification**
This is Facebook's checkpoint/2FA flow. The script pauses and lets you
complete it manually in the visible browser window. Just solve it there
and press Enter in the terminal to continue.

**Comments extraction returns 0 results**
Facebook's DOM (class names, `role` attributes, etc.) changes periodically.
Inspect the live page with Chrome DevTools and update the XPath selectors
in `_comment_blocks()` and `_extract_one()` in `util/scrape.py` accordingly.

**Reel scrolls but does not load more comments**
Check the text and language of the load-more button. Supported English, Urdu,
and Persian labels are handled automatically; an unfamiliar label needs to
be added to `_is_load_more_label()`. Look for `[info] Loading comments/replies:`
in the terminal to confirm a click was made. Keep the side panel open.

**Reel comments panel is not recognized**
Follow the terminal's manual selection prompt and click inside the comments
list. The selected element must have a scrollable ancestor. Press Ctrl+C to
cancel if the panel cannot be selected.

**Account gets flagged or logged out unexpectedly**
This is a known risk of automating Facebook logins, and is to be expected.
Simply move onto the next burner account until it gets got as well, then the next.
