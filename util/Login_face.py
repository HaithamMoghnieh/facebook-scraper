import time
from selenium.webdriver.support import expected_conditions as EC


from selenium.common import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait 

from selenium.webdriver.common.by import By
def _dismiss_cookie_banner(driver):
    """Click through a cookie-consent dialog if Facebook shows one."""
    for phrase in ("Allow all cookies", "Allow essential and optional cookies", "Accept All"):
        try:
            btn = driver.find_element(By.XPATH, f"//span[contains(text(), '{phrase}')]")
            btn.click()
            time.sleep(1)
            return
        except NoSuchElementException:
            continue


def _find_first(driver, locators, wait_seconds=25):
    """Try several (By, value) locators in turn, returning the first match."""
    wait = WebDriverWait(driver, wait_seconds)
    last_error = None
    for by, value in locators:
        try:
            return wait.until(EC.presence_of_element_located((by, value)))
        except TimeoutException as e:
            last_error = e
            continue
    raise last_error


def _debug_dump(driver, label="debug"):
    """Save a screenshot + page title/url so we can see what actually loaded."""
    try:
        driver.save_screenshot(f"{label}.png")
        print(f"\n[debug] Saved screenshot to {label}.png")
        print(f"[debug] Current URL: {driver.current_url}")
        print(f"[debug] Page title: {driver.title}")
    except Exception as e:
        print(f"[debug] Could not capture debug info: {e}")




def _is_checkpoint_url(url: str) -> bool:
    return any(
        marker in url
        for marker in (
            "checkpoint",
            "two_step_verification",
            "two_factor",
            "login_approval",
        )
    )


def _handle_checkpoint(driver):
    _debug_dump(driver, "post_login_checkpoint")
    print(
        "\nFacebook is asking for extra verification (2FA / checkpoint / "
        "captcha) — this usually means it has flagged this login as "
        "automated. A screenshot was saved as post_login_checkpoint.png."
    )
    input(
        "Complete the verification manually in the opened browser window "
        "(enter the code sent to your phone/email/authenticator app), "
        "then press Enter here once you're fully logged in and back on "
        "the normal Facebook feed..."
    )


def login_face(driver, email: str, password: str):
    driver.get("https://www.facebook.com/login")
    time.sleep(3)
    _dismiss_cookie_banner(driver)

    if _is_checkpoint_url(driver.current_url):
        _handle_checkpoint(driver)
        return

    try:
        email_box = _find_first(
            driver,
            [
                (By.ID, "email"),
                (By.NAME, "email"),
                (By.XPATH, "//input[@type='text' and (@name='email' or @id='email')]"),
                (By.XPATH, "//input[contains(@aria-label, 'Email') or contains(@aria-label, 'phone')]"),
            ],
        )
    except TimeoutException:
        if _is_checkpoint_url(driver.current_url):
            _handle_checkpoint(driver)
            return
        _debug_dump(driver, "login_page_not_found")
        raise RuntimeError(
            "Could not find the email field. Facebook likely served a "
            "different page (region variant, cookie wall, or bot check). "
            "Check login_page_not_found.png to see what loaded."
        )

    email_box.click()
    email_box.send_keys(email)

    pass_box = _find_first(driver, [(By.ID, "pass"), (By.NAME, "pass")])
    pass_box.click()
    pass_box.send_keys(password)
    pass_box.submit()

    time.sleep(5)

    if _is_checkpoint_url(driver.current_url) or "login" in driver.current_url:
        _handle_checkpoint(driver)
