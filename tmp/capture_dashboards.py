"""Capture full-page screenshots of all 8 active TRPA dashboards.

Uses Selenium + headless Chrome. Assumes the html-static preview server is
running on http://localhost:8123 (via .claude/launch.json).
"""
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

OUT_DIR = Path(__file__).parent / "dashboard_screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE = "http://localhost:8123/html"

DASHBOARDS = [
    ("01_allocation-tracking",            "allocation-tracking.html",           7),
    ("02_pool-balance-cards",             "pool-balance-cards.html",            4),
    ("03_public-allocation-availability", "public-allocation-availability.html", 3),
    ("04_residential-additions-by-source", "residential-additions-by-source.html", 4),
    ("05_regional-capacity-dial",         "regional-capacity-dial.html",        6),
    ("06_development_history",            "development_history.html",           7),
    ("07_development_history_units",      "development_history_units.html",     7),
    ("08_qa-change-rationale",            "qa-change-rationale.html",           5),
]

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--disable-gpu")
opts.add_argument("--window-size=1400,1000")
opts.add_argument("--hide-scrollbars")
opts.add_argument("--force-device-scale-factor=1")

driver = webdriver.Chrome(options=opts)

try:
    for slug, fname, wait_sec in DASHBOARDS:
        url = f"{BASE}/{fname}"
        print(f"Loading {url} (waiting {wait_sec}s for data)...")
        driver.get(url)
        time.sleep(wait_sec)

        # Resize window to full page height so the screenshot captures everything
        total_h = driver.execute_script(
            "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);"
        )
        driver.set_window_size(1400, max(1000, total_h + 60))
        time.sleep(1.5)  # let any animation/charts settle after resize

        out = OUT_DIR / f"{slug}.png"
        driver.save_screenshot(str(out))
        size_kb = out.stat().st_size / 1024
        print(f"  saved {out.name} ({total_h}px tall, {size_kb:.0f} KB)")
finally:
    driver.quit()

print(f"\nDone. {len(DASHBOARDS)} screenshots in {OUT_DIR}")
