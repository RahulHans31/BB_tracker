"""One-off: fetch one product page with Playwright and print __NEXT_DATA__ structure."""
import json
import re
import sys
from pathlib import Path

# Add parent so we can import set_location_session etc.
sys.path.insert(0, str(Path(__file__).parent))
import requests
from tracker import set_location_session, _add_session_cookies_to_context, PAGE_HEADERS

def main():
    url = "https://www.bigbasket.com/pd/40300424/super-saver-sona-masoori-raw-rice-26-kg-bag/"
    pincode = "122001"
    from playwright.sync_api import sync_playwright
    session = set_location_session(pincode)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=PAGE_HEADERS.get("User-Agent", ""))
        try:
            page = context.new_page()
            page.goto("https://www.bigbasket.com/", wait_until="load", timeout=10000)
            page.close()
        except Exception:
            pass
        _add_session_cookies_to_context(context, session)
        page = context.new_page()
        page.goto(url, wait_until="load", timeout=20000)
        import time
        time.sleep(3)
        html = page.content()
        page.close()
        browser.close()
    # Save HTML sample
    Path("debug_product.html").write_text(html[:150000], encoding="utf-8")
    print("Wrote debug_product.html (first 150k chars)")
    # Parse __NEXT_DATA__
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>([^<]+)</script>', html)
    if not m:
        print("No __NEXT_DATA__ found")
        return
    data = json.loads(m.group(1))
    props = data.get("props", {}).get("pageProps", {})
    print("pageProps keys:", list(props.keys()))
    # Look for store_availability anywhere
    def find_keys(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("store_availability", "availability", "pstat", "out_of_stock", "in_stock"):
                    print(f"  Found at {path}.{k}: {repr(v)[:200]}")
                find_keys(v, f"{path}.{k}")
        elif isinstance(obj, list) and obj and isinstance(obj[0], dict):
            find_keys(obj[0], f"{path}[0]")
    find_keys(props)

if __name__ == "__main__":
    main()
