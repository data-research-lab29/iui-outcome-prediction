"""
Visits a Streamlit Community Cloud app with a real headless browser and,
if the app is showing the "Zzzz... this app has gone to sleep" screen,
clicks the wake-up button. A plain HTTP GET does NOT work for this,
because a sleeping app still returns HTTP 200 with a static HTML shell.

Changes from the previous version:
- Waits up to 45 s for the wake-up button instead of a fixed 5 s, and also
  looks inside iframes, so a slow page is no longer mistaken for "awake".
- Stays on the page for STAY_SECONDS on every run, so the visit opens a
  real session and Streamlit counts it as traffic.
- Prints part of the page text to the log, so you can see what it saw.
- Exits with an error (red X in Actions) if the app fails to wake up.
"""

import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

APP_URL = os.environ.get(
    "STREAMLIT_APP_URL",
    "https://iui-outcome-prediction-memnxer5pxjwx2j6tapp2ry.streamlit.app/",
)

FIND_BUTTON_SECONDS = 45   # how long to look for the wake-up button
WAKE_TIMEOUT_SECONDS = 180  # how long to wait for the app to boot after clicking
STAY_SECONDS = 30          # how long to keep the page open on every run

# Case-insensitive match on the button text.
WAKE_BUTTON_XPATH = (
    "//button[contains(translate(normalize-space(.), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
    "'get this app back up')]"
)


def build_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1696")
    chrome_bin = os.environ.get("CHROME_BIN")
    if chrome_bin:
        options.binary_location = chrome_bin
    driver_bin = os.environ.get("CHROMEDRIVER_BIN")
    service = Service(executable_path=driver_bin) if driver_bin else Service()
    return webdriver.Chrome(service=service, options=options)


def find_wake_button(driver):
    """Return the wake-up button if present, searching the page and its iframes."""
    driver.switch_to.default_content()
    buttons = driver.find_elements(By.XPATH, WAKE_BUTTON_XPATH)
    if buttons:
        return buttons[0]
    for frame in driver.find_elements(By.TAG_NAME, "iframe"):
        try:
            driver.switch_to.frame(frame)
            buttons = driver.find_elements(By.XPATH, WAKE_BUTTON_XPATH)
            if buttons:
                return buttons[0]  # stay inside this frame so .click() works
        except Exception:
            pass
        driver.switch_to.default_content()
    return None


def page_text(driver, limit=300):
    """Title, iframe count, and visible text of the page and of each iframe.

    On *.streamlit.app the app itself runs inside an iframe, so the outer
    page's own text is usually empty; the app text shows up under frame[i].
    """
    parts = []
    try:
        driver.switch_to.default_content()
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        parts.append(f"title={driver.title!r}")
        parts.append(f"iframes={len(frames)}")
        parts.append("top=" + repr(driver.find_element(By.TAG_NAME, "body").text[:limit]))
        for i, frame in enumerate(frames):
            try:
                driver.switch_to.frame(frame)
                text = driver.find_element(By.TAG_NAME, "body").text[:limit]
                parts.append(f"frame[{i}]=" + repr(text))
            except Exception as exc:
                parts.append(f"frame[{i}]=<unreadable: {exc.__class__.__name__}>")
            finally:
                driver.switch_to.default_content()
    except Exception as exc:
        parts.append(f"<could not read page: {exc}>")
    return " ; ".join(parts).replace("\\n", " | ")


def wait_for_button(driver, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        button = find_wake_button(driver)
        if button is not None:
            return button
        time.sleep(2)
    return None


def main():
    try:
        driver = build_driver()
    except Exception as exc:
        print(f"Could not start Chrome: {exc}")
        sys.exit(1)

    try:
        print(f"Visiting {APP_URL} ...")
        driver.get(APP_URL)

        button = wait_for_button(driver, FIND_BUTTON_SECONDS)

        if button is not None:
            print("App was ASLEEP. Clicking the wake-up button ...")
            button.click()
            driver.switch_to.default_content()

            # Wait until the wake-up button is gone for good.
            deadline = time.time() + WAKE_TIMEOUT_SECONDS
            while time.time() < deadline:
                time.sleep(5)
                if find_wake_button(driver) is None:
                    break
            else:
                print("ERROR: the app did not wake up within "
                      f"{WAKE_TIMEOUT_SECONDS} s. Page check: {page_text(driver)}")
                sys.exit(1)
            print("App woke up.")
        else:
            print("No wake-up button found, so the app looks AWAKE.")

        print(f"Keeping the page open for {STAY_SECONDS} s so the visit counts ...")
        time.sleep(STAY_SECONDS)
        print(f"Page check: {page_text(driver)}")
        print("Done.")

    except Exception as exc:
        print(f"ping_app.py failed: {exc}")
        sys.exit(1)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
