import time
import re
import unicodedata

from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By

def _get_search_scope(driver):
    """Return the dialog element if the post opened as a modal, otherwise
    None to mean 'search the whole page'."""
    try:
        return driver.find_element(By.XPATH, "//div[@role='dialog']")
    except NoSuchElementException:
        return None


def _debug_list_load_more_buttons(driver, scope=None):
    """One-time diagnostic: print anything that looks like a 'load more
    comments/replies' control — including its outer HTML — so selectors
    can be tuned to what Facebook is really showing instead of guessed
    phrases."""
    scope = scope if scope is not None else _get_search_scope(driver)
    base = ".//" if scope is not None else "//"
    try:
        elements = []
        for tag in ("span", "div[@role='button']", "a"):
            xpath = f"{base}{tag}"
            found = scope.find_elements(By.XPATH, xpath) if scope is not None \
                else driver.find_elements(By.XPATH, xpath)
            elements.extend(found)

        seen_html = set()
        printed = 0
        for el in elements:
            try:
                txt = el.text.strip()
            except StaleElementReferenceException:
                continue
            if not txt or len(txt) > 60:
                continue
            lowered = txt.lower()
            if "comment" in lowered or "repl" in lowered or "more" in lowered:
                try:
                    outer = el.get_attribute("outerHTML")
                except StaleElementReferenceException:
                    continue
                snippet = outer[:300] if outer else ""
                if snippet in seen_html:
                    continue
                seen_html.add(snippet)
                print(f"[debug] Candidate: text={txt!r}")
                print(f"        html={snippet}")
                printed += 1
        if printed == 0:
            print("[debug] No comment/reply/more-like elements found on the page.")
    except Exception as e:
        print(f"[debug] Could not list buttons: {e}")
        


def get_post_title(driver) -> str:
    """Best-effort grab of the original post's own text, before comments."""
    try:
        candidates = driver.find_elements(
            By.XPATH, "//div[@data-ad-preview='message']"
        )
        if candidates:
            return candidates[0].text.strip()[:500]
    except NoSuchElementException:
        pass
    try:
        candidates = driver.find_elements(By.XPATH, "//div[@dir='auto']")
        for c in candidates:
            txt = c.text.strip()
            if len(txt) > 20:
                return txt[:500]
    except NoSuchElementException:
        pass
    return ""
def _extract_one(block, post_url: str, post_title: str, seen_keys: set):
    """Pull fields out of a single comment block. Returns None if it's a
    duplicate or doesn't look like a real comment."""
    try:
        author_link_el = block.find_element(By.XPATH, ".//a[@role='link' and @href]")
        author_url = author_link_el.get_attribute("href")
    except NoSuchElementException:
        author_url = ""

    try:
        author_el = block.find_element(By.XPATH, ".//a[@role='link']//span")
        author = author_el.text.strip()
    except NoSuchElementException:
        author = ""

    try:
        text_el = block.find_element(By.XPATH, ".//div[@dir='auto' and not(@role)]")
        text = text_el.text.strip()
    except NoSuchElementException:
        text = ""

    if not text:
        return None

    profile_id = _extract_profile_id(author_url)
    dedup_key = (profile_id or author, text)
    if dedup_key in seen_keys:
        return None
    seen_keys.add(dedup_key)

    try:
        pic_el = block.find_element(By.XPATH, ".//image | .//img")
        profile_picture = pic_el.get_attribute("xlink:href") or pic_el.get_attribute("src")
    except NoSuchElementException:
        profile_picture = ""

    try:
        like_el = block.find_element(By.XPATH, ".//span[contains(@aria-label, 'like')]")
        likes = like_el.text.strip()
    except NoSuchElementException:
        likes = ""

    try:
        time_el = block.find_element(By.TAG_NAME, "abbr")
        timestamp = time_el.get_attribute("title") or time_el.text
    except NoSuchElementException:
        timestamp = ""

    try:
        comment_link_el = block.find_element(
            By.XPATH, ".//a[contains(@href, 'comment_id')]"
        )
        comment_url = comment_link_el.get_attribute("href")
    except NoSuchElementException:
        comment_url = ""

    try:
        ancestors = block.find_elements(By.XPATH, "ancestor::div[@role='article']")
        threading_depth = len(ancestors)
    except StaleElementReferenceException:
        threading_depth = 0

    return {
        "inputUrl": post_url,
        "postTitle": post_title,
        "profileId": profile_id,
        "profileName": author,
        "profilePicture": profile_picture,
        "text": text,
        "likesCount": likes,
        "threadingDepth": threading_depth,
        "commentUrl": comment_url,
        "timestamp": timestamp,
        "pageAdLibrary/id": "",
        "pageAdLibrary/is_business_page_active": "",
    }



def _get_scroll_container(driver, comments_only=False):
    """Find the element that actually scrolls the comments feed. Modern
    Facebook pages frequently keep <body> non-scrolling and put the real
    scrollable viewport on some inner app-root div — this is true both
    for modal/dialog posts AND normal permalink pages, so search the
    whole document, not just inside a dialog if one exists."""
    js = """
    const selected = window.__fbCommentsScroll;
    if (arguments[0] && selected && selected.isConnected &&
        selected.getBoundingClientRect().height > 0) return selected;
    const visible = el => {
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight;
    };
    if (arguments[0]) {
        // Reel comments can live in an aside without role=article comments.
        const panels = [...document.querySelectorAll('[role="complementary"]')]
            .filter(el => visible(el) && !el.querySelector('video'));
        const ranked = panels.map(panel => {
            const evidence = panel.querySelectorAll(
                '[role="article"], a[href*="comment_id"], [aria-label^="Comment by"]'
            ).length;
            const scrollables = [panel, ...panel.querySelectorAll('*')].filter(el =>
                visible(el) && el.clientHeight > 80 &&
                /auto|scroll/.test(getComputedStyle(el).overflowY));
            scrollables.sort((a, b) => {
                const count = el => el.querySelectorAll(
                    '[role="article"], a[href*="comment_id"]'
                ).length;
                return count(b) - count(a) ||
                    (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight);
            });
            return {panel, evidence, scroll: scrollables[0]};
        }).filter(item => item.scroll);
        ranked.sort((a, b) => b.evidence - a.evidence);
        if (ranked.length && (ranked[0].evidence > 0 || panels.length === 1))
            return ranked[0].scroll;
    }
    // Prefer a scrollable ancestor of actual comments over the video/feed.
    const candidates = new Map();
    for (const article of document.querySelectorAll(
        '[role="article"], a[href*="comment_id"], [aria-label^="Comment by"]')) {
        if (!visible(article)) continue;
        const isComment = article.matches('a[href*="comment_id"], [aria-label^="Comment by"]') ||
            article.querySelector('a[href*="comment_id"]') ||
            (article.querySelector('a[role="link"]') &&
             article.querySelector('div[dir="auto"]') && !article.querySelector('video'));
        if (!isComment) continue;
        let distance = 0;
        for (let el = article.parentElement; el && el !== document.body; el = el.parentElement) {
            distance++;
            const style = getComputedStyle(el);
            if (visible(el) && /auto|scroll/.test(style.overflowY) && el.clientHeight > 0) {
                const score = 100 / distance;
                candidates.set(el, (candidates.get(el) || 0) + score);
            }
        }
    }
    if (candidates.size) {
        return [...candidates].sort((a, b) => b[1] - a[1])[0][0];
    }
    if (arguments[0]) return null;
    function findScrollable(el, best) {
        if (!el) return best;
        const style = window.getComputedStyle(el);
        const canScroll = (style.overflowY === 'auto' || style.overflowY === 'scroll');
        const overflowAmount = el.scrollHeight - el.clientHeight;
        if (canScroll && overflowAmount > 100) {
            if (!best || overflowAmount > best.overflowAmount) {
                best = { el: el, overflowAmount: overflowAmount };
            }
        }
        for (const child of el.children) {
            best = findScrollable(child, best);
        }
        return best;
    }
    const result = findScrollable(document.body, null);
    return result ? result.el : null;
    """
    try:
        return driver.execute_script(js, comments_only)
    except Exception:
        return None

def _prepare_reel_comments(driver):
    """Open comments, with a manual fallback for unfamiliar Facebook layouts."""
    if _get_scroll_container(driver, comments_only=True) is not None:
        return
    buttons = driver.find_elements(
        By.XPATH,
        "//*[@role='button' or self::button][contains(translate(@aria-label, "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'comment')]",
    )
    for button in buttons:
        try:
            if button.is_displayed():
                button.click()
                time.sleep(2)
                if _get_scroll_container(driver, comments_only=True) is not None:
                    return
        except Exception:
            continue
    input("Open the reel's comments panel in Chrome, then press Enter here...")
    while _get_scroll_container(driver, comments_only=True) is None:
        _select_reel_comments(driver)


def _select_reel_comments(driver):
    """Let the user identify an unfamiliar panel without relying on FB labels."""
    driver.execute_script("""
        window.__fbCommentsScroll = null;
        if (window.__fbCommentsPicker)
            document.removeEventListener('click', window.__fbCommentsPicker, true);
        window.__fbCommentsPicker = function(event) {
            for (let el = event.target; el && el !== document.body; el = el.parentElement) {
                const style = getComputedStyle(el);
                if (/auto|scroll/.test(style.overflowY) && el.clientHeight > 0 &&
                    !el.querySelector('video')) {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                    window.__fbCommentsScroll = el;
                    document.removeEventListener('click', window.__fbCommentsPicker, true);
                    return;
                }
            }
        };
        document.addEventListener('click', window.__fbCommentsPicker, true);
    """)
    try:
        input("Panel not recognized. Click a comment inside the side comments list in Chrome, then press Enter here (Ctrl+C to cancel)...")
    finally:
        driver.execute_script("""
            document.removeEventListener('click', window.__fbCommentsPicker, true);
            delete window.__fbCommentsPicker;
        """)


def _normalize_control_text(text):
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    return " ".join(text.translate(str.maketrans({"ك": "ک", "ي": "ی", "ى": "ی"})).split())


def _is_load_more_label(text):
    """English, Urdu and Persian comment/reply pagination labels."""
    txt = _normalize_control_text(text)
    more_words = ("more", "previous", "older", "next", "مزید", "بیشتر", "قبلی")
    comment_words = ("comment", "repl", "کمنٹ", "کمنٹس", "تبصر", "جواب", "پاسخ", "نظر", "دیدگاه", "نظرات")
    return bool(
        (any(word in txt for word in more_words) and any(word in txt for word in comment_words))
        or re.match(r"^(?:view\s+)?\d+\s+repl", txt)
        or re.search(r"\d+\s*(?:جواب|پاسخ)", txt)
    )


def _load_more_comments(driver, scope, is_reel=False):
    """Click one batch/reply control, then let the next round re-query the DOM."""
    if is_reel:
        # A footer can be a sibling of the scrolling list. Expand only within
        # the narrow comments panel, never into the surrounding reel viewer.
        scope = driver.execute_script("""
            let panel = arguments[0];
            const aside = panel.closest('[role="complementary"]');
            if (aside && !aside.querySelector('video')) return aside;
            const width = panel.getBoundingClientRect().width;
            for (let i = 0; i < 3 && panel.parentElement; i++) {
                const parent = panel.parentElement;
                if (parent === document.body || parent.querySelector('video') ||
                    parent.getBoundingClientRect().width > width * 1.5) break;
                panel = parent;
            }
            return panel;
        """, scope)
    root = scope if scope is not None else driver
    prefix = ".//" if scope is not None else "//"
    candidates = root.find_elements(
        By.XPATH, prefix + "*[self::span or self::a or self::button or @role='button']"
    )
    for element in candidates:
        try:
            if not element.is_displayed() or not element.is_enabled():
                continue
            labels = [element.text, element.get_attribute("aria-label") or ""]
            txt = next((_normalize_control_text(label) for label in labels
                        if _is_load_more_label(label)), _normalize_control_text(labels[0]))
            if not txt or len(txt) > 100:
                continue
            explicit = _is_load_more_label(txt)
            # Plain 'More' is used by some reel pagination controls. Exclude
            # comment bodies and post menus so we don't expand unrelated text.
            generic = is_reel and txt in ("more", "load more", "view more", "see more")
            if not explicit and not generic:
                continue
            if generic and element.find_elements(By.XPATH, "ancestor::*[@role='article']"):
                continue
            if generic and element.get_attribute("aria-haspopup") in ("true", "menu"):
                continue
            if not is_reel:
                driver.execute_script("arguments[0].scrollIntoView(true);", element)
            element.click()
            print(f"[info] Loading comments/replies: {txt}")
            time.sleep(2)
            return True
        except Exception:
            continue
    return False


def scrape_comments(driver, post_url: str, max_comments: int, content_type=None):
    driver.get(post_url)
    time.sleep(4)

    resolved_url = driver.current_url
    if resolved_url != post_url:
        print(f"[debug] URL redirected to: {resolved_url}")
        print("[debug] Reloading that resolved URL directly (share/p/ links sometimes render a limited preview template on first load).")
        driver.get(resolved_url)
        time.sleep(4)

    is_reel = content_type == "reel" or (
        content_type is None and any(
            re.search(r"/(?:reel|reels|share/r)(?:/|\?|$)", url)
            for url in (post_url, resolved_url)
        )
    )
    if is_reel:
        _prepare_reel_comments(driver)
    scroll_container = _get_scroll_container(driver, comments_only=is_reel)
    if is_reel and scroll_container is None:
        raise RuntimeError("Could not identify the reel comments scroll area. Keep the side panel open with comments visible and retry.")
    post_title = get_post_title(driver)

    # Try to switch comment sort to "All comments" for a fuller thread.
    sort_switched = False
    try:
        sort_scope = scroll_container if is_reel else driver
        sort_button = sort_scope.find_element(
            By.XPATH, ".//span[contains(text(), 'Most relevant')]"
        )
        sort_button.click()
        time.sleep(1)
        driver.find_element(
            By.XPATH, "//span[contains(text(), 'All comments')]"
        ).click()
        time.sleep(3)
        sort_switched = True
    except NoSuchElementException:
        pass

    print(
        f"[debug] Comment sort switched to 'All comments': {sort_switched}"
        + ("" if sort_switched else " — no sort menu found; may already be showing a limited/curated set")
    )

    collected = {}
    seen_keys = set()
    stagnant_rounds = 0
    max_stagnant_rounds = 8
    round_num = 0
    last_raw_count = 0
    load_rounds_without_progress = 0

    scroll_container = _get_scroll_container(driver, comments_only=is_reel)
    if scroll_container is not None:
        print("[info] Found an inner scrollable container — scrolling that instead of the window.")
    else:
        print("[info] No inner scrollable container found — scrolling the window.")

    while stagnant_rounds < max_stagnant_rounds and len(collected) < max_comments:
        round_num += 1

        if round_num == 1:
            _debug_list_load_more_buttons(driver, scroll_container if is_reel else None)

        if is_reel:
            scroll_container = _get_scroll_container(driver, comments_only=True)
            if scroll_container is None:
                _select_reel_comments(driver)
                scroll_container = _get_scroll_container(driver, comments_only=True)
                if scroll_container is None:
                    continue
        scope = scroll_container if is_reel else _get_search_scope(driver)

        # Extract from whatever is currently in the DOM RIGHT NOW, before
        # scrolling moves it out of view and Facebook prunes it.
        raw_blocks = _comment_blocks(scroll_container if is_reel else driver, scoped=is_reel)
        before = len(collected)
        for block in raw_blocks:
            try:
                row = _extract_one(block, post_url, post_title, seen_keys)
            except StaleElementReferenceException:
                continue
            if row:
                key = (row["profileId"] or row["profileName"], row["text"])
                collected[key] = row

        new_this_round = len(collected) - before
        print(
            f"[progress] round {round_num}: {len(raw_blocks)} comment "
            f"elements currently in page, {len(collected)} unique "
            f"collected so far"
        )

        # Save this batch before clicking: pagination may replace its DOM.
        if len(collected) >= max_comments:
            break
        clicked_something = _load_more_comments(driver, scope, is_reel)
        if clicked_something:
            load_rounds_without_progress = (load_rounds_without_progress + 1
                                            if new_this_round == 0 else 0)
            if load_rounds_without_progress >= max_stagnant_rounds:
                print("[info] Load-more controls are not producing new comments; stopping.")
                break
            # Read the newly loaded batch before scrolling can virtualize it.
            stagnant_rounds = 0
            continue

        raw_count_changed = len(raw_blocks) != last_raw_count
        last_raw_count = len(raw_blocks)

        if new_this_round == 0 and not clicked_something and not raw_count_changed:
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0

        # Re-locate the scroll container each round in case the DOM
        # changed (e.g. dialog remounted).
        scroll_container = _get_scroll_container(driver, comments_only=is_reel)
        if is_reel and scroll_container is None:
            _select_reel_comments(driver)
            continue
        try:
            before_pos = driver.execute_script(
                "return arguments[0] ? arguments[0].scrollTop : window.scrollY;",
                scroll_container,
            )
        except Exception:
            before_pos = None
        _scroll_down(driver, scroll_container)
        time.sleep(2)
        try:
            after_pos = driver.execute_script(
                "return arguments[0] ? arguments[0].scrollTop : window.scrollY;",
                scroll_container,
            )
        except Exception:
            after_pos = None
        if before_pos is not None and after_pos is not None:
            print(f"[debug] scroll position: {before_pos} -> {after_pos}")

    return list(collected.values())[:max_comments]

def _extract_profile_id(url: str) -> str:
    """Pull a numeric FB id or vanity username out of a profile URL."""
    if not url:
        return ""
    m = re.search(r"[?&]id=(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"facebook\.com/([^/?&]+)", url)
    if m:
        return m.group(1)
    return ""


def _comment_blocks(driver, scoped=False):
    blocks = driver.find_elements(By.XPATH, ".//div[@role='article']" if scoped else "//div[@role='article']")
    if blocks or not scoped:
        return blocks
    # Some reel layouts omit role=article. Use the nearest comment wrapper
    # containing both an author link and comment text, not the whole panel.
    return driver.find_elements(
        By.XPATH,
        ".//a[contains(@href, 'comment_id')]/ancestor::div["
        ".//a[@role='link']//span and .//div[@dir='auto' and not(@role)]][1]"
        " | .//div[starts-with(@aria-label, 'Comment by')]",
    )

def _scroll_down(driver, container):
    if container is not None:
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollTop + 700;", container
        )
    else:
        driver.execute_script("window.scrollBy(0, 700);")
        
        
