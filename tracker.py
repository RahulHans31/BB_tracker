"""
BigBasket stock checker by pincode.

Checks stock for given product URLs and pincodes.
- Requests mode: session file or pincode API (may get Access Denied).
- Browser mode: real Chrome (like deepakksahu/bigbasket_slot_notifier) - set pincode once, then check.
Run: python tracker.py -c   (uses config.json)
     python tracker.py -c --browser   (use Chrome; no Access Denied)
"""

import argparse
import base64
import json
import re
import sys
import time
import uuid
from pathlib import Path

import requests

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / "config.json"
STATE_FILE = BASE / "state.json"
PINCODE_FLOW_FILE = BASE / "pincode_flow.json"
PINCODE_SESSION_RECORD_FILE = BASE / "pincode_session_record.json"

# -----------------------------------------------------------------------------
# Headers (single set; keep it simple)
# -----------------------------------------------------------------------------

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.bigbasket.com/",
}
API_HEADERS = {
    **HEADERS,
    "Accept": "application/json, text/plain, */*",
    "x-channel": "BB-WEB",
    "x-entry-context-id": "100",
}

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def load_json(path: Path, default):
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def parse_product_url(url: str):
    """Return (product_id, slug) or (None, None)."""
    m = re.search(r"bigbasket\.com/pd/(\d+)/([^/?]+)", url, re.I)
    if m:
        return m.group(1), m.group(2).strip("/")
    return None, None


def _send_telegram_to_chat(config: dict, chat_id: str | int, text: str) -> bool:
    """Send a Telegram message to a specific chat_id. Uses telegram_bot_token from config. No topic. Returns True if sent."""
    if not config:
        return False
    token = str(config.get("telegram_bot_token") or "").strip()
    cid = str(chat_id).strip() if chat_id is not None and str(chat_id).strip() else ""
    if not token or not cid:
        return False
    try:
        data = {"chat_id": cid, "text": text}
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            timeout=15,
        )
        if not r.ok:
            print(f"  Telegram error {r.status_code}: {r.text}", file=sys.stderr)
            return False
        return True
    except Exception as e:
        print(f"  (Telegram error: {e})", file=sys.stderr)
        return False


def _send_telegram_photo(config: dict, photo_bytes: bytes, caption: str) -> bool:
    """Send a Telegram photo with caption. Uses telegram_chat_id and optional topic_id. Returns True if sent."""
    if not config or not photo_bytes:
        return False
    token = str(config.get("telegram_bot_token") or "").strip()
    chat_id_raw = config.get("telegram_chat_id")
    chat_id = str(chat_id_raw).strip() if chat_id_raw is not None and str(chat_id_raw).strip() else ""
    if not token or not chat_id:
        return False
    try:
        files = {"photo": ("screenshot.png", photo_bytes, "image/png")}
        data = {"chat_id": chat_id, "caption": caption[:1024]}
        topic_id = config.get("telegram_topic_id")
        if topic_id is not None and str(topic_id).strip():
            data["message_thread_id"] = int(topic_id) if isinstance(topic_id, (int, float)) else int(str(topic_id).strip())
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data=data,
            files=files,
            timeout=20,
        )
        if not r.ok:
            print(f"  Telegram photo error {r.status_code}: {r.text[:150]}", file=sys.stderr)
            return False
        print("  (Telegram photo sent)")
        return True
    except Exception as e:
        print(f"  (Telegram photo error: {e})", file=sys.stderr)
        return False


def _send_telegram(config: dict, text: str, silent_if_missing: bool = False) -> bool:
    """Send a Telegram message. Config: telegram_bot_token, telegram_chat_id, telegram_topic_id (optional). Returns True if sent."""
    if not config:
        return False
    token = str(config.get("telegram_bot_token") or "").strip()
    chat_id_raw = config.get("telegram_chat_id")
    chat_id = str(chat_id_raw).strip() if chat_id_raw is not None and str(chat_id_raw).strip() else ""
    if not token or not chat_id:
        if not silent_if_missing:
            print("  (Telegram skipped: set telegram_bot_token and telegram_chat_id in config)", file=sys.stderr)
        return False
    try:
        # Use form data (Telegram accepts both JSON and form)
        data = {"chat_id": chat_id, "text": text}
        topic_id = config.get("telegram_topic_id")
        if topic_id is not None and str(topic_id).strip():
            data["message_thread_id"] = int(topic_id) if isinstance(topic_id, (int, float)) else int(str(topic_id).strip())
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            timeout=15,
        )
        if not r.ok:
            print(f"  Telegram error {r.status_code}: {r.text}", file=sys.stderr)
            return False
        print("  (Telegram sent)")
        return True
    except Exception as e:
        print(f"  (Telegram error: {e})", file=sys.stderr)
        return False


def _send_telegram_error(config: dict, title: str, pincode: str, url: str, error_detail: str) -> None:
    """Send an error alert to telegram_error_chat_id (e.g. 7992845749)."""
    if not config:
        return
    chat_id_raw = config.get("telegram_error_chat_id")
    chat_id = str(chat_id_raw).strip() if chat_id_raw is not None and str(chat_id_raw).strip() else ""
    if not chat_id:
        return
    text = f"BigBasket tracker – ERROR\n\nProduct: {title or 'Unknown'}"
    if pincode:
        text += f"\nPincode: {pincode}"
    text += f"\nError: {error_detail or 'Check failed'}"
    if url:
        text += f"\n\nLink:\n{url}"
    _send_telegram_to_chat(config, chat_id, text)


def _send_telegram_in_stock(config: dict, change: dict) -> None:
    """Send a Telegram alert when a product is back in stock."""
    if not config or (change.get("to") or "") != "in_stock":
        return
    title = change.get("title") or "Product"
    pincode = change.get("pincode") or ""
    url = (change.get("url") or "").strip()
    text = f"BigBasket: {title} is back in stock"
    if pincode:
        text += f" @ pincode {pincode}"
    text += "\n\nProduct link:\n" + url if url else "\n\n(No link)"
    _send_telegram(config, text, silent_if_missing=False)


def _headers_from_har(har_data: dict) -> dict | None:
    """
    Extract request headers from a HAR file. Uses the last request to bigbasket.com
    (most complete Cookie). Returns dict of header name -> value or None.
    """
    try:
        entries = har_data.get("log", {}).get("entries") or []
    except Exception:
        return None
    if not isinstance(entries, list):
        return None
    # Collect all requests to bigbasket.com; take the last one (most recent cookies)
    bigbasket_entries = [
        e for e in entries
        if isinstance(e, dict)
        and "bigbasket.com" in (e.get("request") or {}).get("url", "")
    ]
    if not bigbasket_entries:
        return None
    req = bigbasket_entries[-1].get("request") or {}
    har_headers = req.get("headers") or []
    if not isinstance(har_headers, list):
        return None
    headers = {}
    for h in har_headers:
        if isinstance(h, dict) and "name" in h and "value" in h:
            name = (h.get("name") or "").strip()
            # Skip HTTP/2 pseudo-headers (:authority, :method, etc.)
            if name and not name.startswith(":"):
                headers[name] = (h.get("value") or "").strip()
    # If HAR has request.cookies, build Cookie header (Chrome sometimes omits it)
    req_cookies = req.get("cookies") or []
    if isinstance(req_cookies, list) and req_cookies:
        cookie_parts = []
        for c in req_cookies:
            if isinstance(c, dict) and c.get("name") and "value" in c:
                cookie_parts.append(f"{c['name']}={c.get('value', '')}")
        if cookie_parts:
            headers["Cookie"] = "; ".join(cookie_parts)
    return headers if headers else None


def load_session_from_file(path: str | Path) -> dict | None:
    """
    Load headers from a file (inspired by shatadru/big_basket_automation).
    Same idea as deepakksahu/bigbasket_slot_notifier (real user session) but via
    exported headers instead of a live browser.
    Supports:
    - HAR file (JSON with log.entries): uses last request to bigbasket.com.
    - cURL: file starts with "curl ", parse -H "Name: value".
    - Plain: each line "Name: value" (e.g. Cookie: ...).
    Returns dict of headers or None on failure.
    """
    path = Path(path)
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return None
    if not raw:
        return None

    # 1. Try HAR (JSON with log.entries)
    if raw.lstrip().startswith("{"):
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "log" in data and "entries" in (data.get("log") or {}):
                headers = _headers_from_har(data)
                if headers:
                    return headers
        except (json.JSONDecodeError, TypeError):
            pass

    headers = {}
    if raw.lstrip().startswith("curl "):
        # Normalize Windows cURL (^" and ^\^" from "Copy as cURL" in Chrome on Windows)
        raw = raw.replace('^"', '"').replace('^\\^"', '"')
        # Parse curl: -H "Key: value" or -H 'Key: value'
        for m in re.finditer(r'-H\s+["\']([^:]+):\s*([^"\']*)["\']', raw):
            key, val = m.group(1).strip(), m.group(2).strip()
            if key:
                headers[key] = val
    else:
        # Simple format: one header per line, "Name: value"
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                key, val = k.strip(), v.strip()
                if key:
                    headers[key] = val
    return headers if headers else None


def set_pincode_session(pincode: str) -> requests.Session | None:
    """
    Use BigBasket's API to set delivery location; return session with cookies.
    autocomplete -> details -> serviceable.
    """
    s = requests.Session()
    s.headers.update(API_HEADERS)
    pin = pincode.strip()
    try:
        # 1. Autocomplete
        r1 = s.get(
            "https://www.bigbasket.com/places/v1/places/autocomplete/",
            params={"inputText": pin, "token": uuid.uuid4().hex[:32]},
            timeout=10,
        )
        if not r1.ok:
            return None
        data = r1.json()
        preds = data.get("predictions") or data.get("results") or data.get("places") or []
        if not preds:
            return None
        first = preds[0] if isinstance(preds[0], dict) else preds
        place_id = first.get("place_id") or first.get("id") or first.get("placeId")
        if not place_id:
            return None

        # 2. Details
        r2 = s.get(
            "https://www.bigbasket.com/places/v1/places/details/",
            params={"placeId": place_id, "token": uuid.uuid4().hex[:32]},
            timeout=10,
        )
        if not r2.ok:
            return None
        details = r2.json()
        lat = details.get("lat") or details.get("latitude")
        lng = details.get("lng") or details.get("longitude")
        if lat is None or lng is None:
            loc = details.get("geometry", {}).get("location", details)
            lat = lat or loc.get("lat")
            lng = lng or loc.get("lng")
        if lat is None or lng is None:
            return None

        # 3. Serviceable (sets location cookies)
        r3 = s.get(
            "https://www.bigbasket.com/ui-svc/v1/serviceable/",
            params={"lat": lat, "lng": lng, "send_all_serviceability": "true"},
            timeout=10,
        )
        if not r3.ok:
            return None
        return s
    except requests.RequestException:
        return None


def fetch_product_page(url: str, session: requests.Session) -> str | None:
    """Fetch product page HTML. Returns None on failure or Access Denied."""
    try:
        r = session.get(url, headers=HEADERS, timeout=15)
        if not r.ok:
            return None
        text = r.text
        if "Access Denied" in text or "access denied" in text.lower():
            return None
        return text
    except requests.RequestException:
        return None


def _find_stock_in_obj(obj, depth: int = 0) -> tuple[str | None, str | None]:
    """Recurse through dict for store_availability / pstat. Returns (status, title) or (None, None)."""
    if depth > 10 or not isinstance(obj, dict):
        return None, None
    av = obj.get("store_availability") or obj.get("storeAvailability") or obj.get("availability")
    if isinstance(av, list) and av:
        pstats = [x.get("pstat") for x in av if isinstance(x, dict)]
        if any(p == "A" for p in pstats):
            t = (obj.get("p_desc") or obj.get("product_name") or obj.get("title") or "").strip()
            return "in_stock", t or None
        if all(p == "O" for p in pstats):
            t = (obj.get("p_desc") or obj.get("product_name") or obj.get("title") or "").strip()
            return "out_of_stock", t or None
    for v in obj.values():
        if isinstance(v, dict):
            s, t = _find_stock_in_obj(v, depth + 1)
            if s:
                return s, t
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    s, t = _find_stock_in_obj(item, depth + 1)
                    if s:
                        return s, t
    return None, None


def parse_stock_from_page_props(props: dict) -> tuple[str, str | None]:
    """
    Parse stock from product pageProps JSON (same as _next/data/.../pd/{id}/{slug}.json).
    Returns (status, title) where status is in_stock | out_of_stock | unknown.
    """
    if not isinstance(props, dict):
        return "unknown", None
    status, title = _find_stock_in_obj(props)
    if status:
        return status, title
    return "unknown", None


def get_build_id_from_html(html: str) -> str | None:
    """Extract Next.js buildId from page HTML (__NEXT_DATA__ or _next/data/...)."""
    if not html:
        return None
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>([^<]+)</script>', html)
    if m:
        try:
            data = json.loads(m.group(1))
            bid = data.get("buildId")
            if bid:
                return bid
        except (json.JSONDecodeError, TypeError):
            pass
    m = re.search(r'/_next/data/([a-zA-Z0-9_-]+)/', html)
    if m:
        return m.group(1)
    return None


def parse_stock_from_html(html: str) -> tuple[str, str | None]:
    """
    Parse stock from product page HTML.
    Returns (status, title) where status is in_stock | out_of_stock | unknown.
    """
    if not html or len(html) < 500:
        return "unknown", None

    # 1. __NEXT_DATA__
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>([^<]+)</script>', html)
    if m:
        try:
            data = json.loads(m.group(1))
            props = data.get("props", {}).get("pageProps", {})
            if isinstance(props, dict):
                status, title = _find_stock_in_obj(props)
                if status:
                    return status, title
        except (json.JSONDecodeError, KeyError):
            pass

    # 2. Text fallback
    low = html.lower()
    if re.search(r"notify\s*me|out\s*of\s*stock|currently\s*unavailable|notify\s*when", low):
        return "out_of_stock", None
    if re.search(r"add\s*to\s*basket|add\s*to\s*cart|buy\s*now", low):
        return "in_stock", None
    return "unknown", None


def check_one_via_api_in_browser(driver, pid: str, slug: str, build_id: str) -> tuple[str | None, str | None]:
    """
    Check stock by fetching product JSON API in the browser (uses current cookies/location).
    Returns (status, title) or (None, None) on error. status is in_stock | out_of_stock | unknown.
    """
    if not build_id or not pid or not slug:
        return None, None
    js = """
    var buildId = arguments[0], pid = arguments[1], slug = arguments[2], callback = arguments[3];
    var url = 'https://www.bigbasket.com/_next/data/' + buildId + '/pd/' + pid + '/' + slug + '.json';
    fetch(url, { credentials: 'include' })
    .then(function(r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function(data) { callback(data); })
    .catch(function() { callback(null); });
    """
    try:
        data = driver.execute_async_script(js, build_id, pid, slug)
        if not data or not isinstance(data, dict):
            return None, None
        props = data.get("pageProps", data)
        if not isinstance(props, dict):
            return None, None
        status, title = parse_stock_from_page_props(props)
        return status, title
    except Exception:
        return None, None


def check_one(url: str, pincode: str, session: requests.Session) -> dict:
    """
    Check one product for one pincode. Returns dict with url, product_id, slug, title, status, error.
    """
    pid, slug = parse_product_url(url)
    if not pid or not slug:
        return {"url": url, "product_id": None, "slug": None, "title": None, "status": "error", "error": "Invalid URL"}

    html = fetch_product_page(url, session)
    if not html:
        return {
            "url": url,
            "product_id": pid,
            "slug": slug,
            "title": slug.replace("-", " ").title(),
            "status": "error",
            "error": "Failed to fetch or Access Denied",
        }

    status, title = parse_stock_from_html(html)
    if not title:
        title = slug.replace("-", " ").title()
    return {"url": url, "product_id": pid, "slug": slug, "title": title, "status": status, "error": None}


# -----------------------------------------------------------------------------
# Browser mode (like deepakksahu/bigbasket_slot_notifier: real Chrome, no Access Denied)
# -----------------------------------------------------------------------------


def _get_driver(headless: bool = False):
    """Create Chrome WebDriver using webdriver-manager. Returns driver or None."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError as e:
        print("Browser mode needs: pip install selenium webdriver-manager", file=sys.stderr)
        return None
    try:
        opts = Options()
        if headless:
            opts.add_argument("--headless=new")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        print(f"Could not start Chrome: {e}", file=sys.stderr)
        return None


# JS to record clicks and inputs in main doc AND all same-origin iframes; builds window.top._bbRecordedSteps
_RECORD_PINCODE_JS = """
(function() {
  var top = window.top;
  top._bbRecordedSteps = top._bbRecordedSteps || [];
  function getSelector(el) {
    if (!el || el.nodeType !== 1) return null;
    try {
      if (el.id && typeof el.id === 'string' && /^[a-zA-Z][\\w.-]*$/.test(el.id))
        return { by: 'id', value: el.id };
      if (el.getAttribute && el.getAttribute('data-testid'))
        return { by: 'css', value: '[data-testid="' + el.getAttribute('data-testid').replace(/"/g, '\\\\"') + '"]' };
      if (el.placeholder && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'))
        return { by: 'xpath', value: '//' + el.tagName.toLowerCase() + '[@placeholder="' + (el.placeholder || '').replace(/"/g, '\\\\"') + '"]' };
      if (el.name && (el.tagName === 'INPUT' || el.tagName === 'SELECT'))
        return { by: 'xpath', value: '//' + el.tagName.toLowerCase() + '[@name="' + (el.name || '').replace(/"/g, '\\\\"') + '"]' };
      var path = [], cur = el;
      while (cur && cur.nodeType === 1) {
        var idx = 1, sib = cur.previousElementSibling;
        while (sib) { if (sib.tagName === cur.tagName) idx++; sib = sib.previousElementSibling; }
        path.unshift(cur.tagName.toLowerCase() + '[' + idx + ']');
        cur = cur.parentElement;
      }
      return { by: 'xpath', value: '//' + path.join('/') };
    } catch (e) { return null; }
  }
  function addListeners(doc) {
    if (!doc || doc._bbRecorderInjected) return;
    doc._bbRecorderInjected = true;
    function saveSteps() {
      try { top.sessionStorage.setItem('_bbRecordedSteps', JSON.stringify(top._bbRecordedSteps)); } catch (e) {}
    }
    doc.addEventListener('click', function(e) {
      var s = getSelector(e.target);
      if (s) { top._bbRecordedSteps.push({ action: 'click', by: s.by, value: s.value }); saveSteps(); }
    }, true);
    doc.addEventListener('input', function(e) {
      var s = getSelector(e.target);
      if (s && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) {
        top._bbRecordedSteps.push({ action: 'send_keys', by: s.by, value: s.value, inputValue: '<PIN>' }); saveSteps();
      }
    }, true);
    doc.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        var s = getSelector(e.target);
        if (s) { top._bbRecordedSteps.push({ action: 'send_keys', by: s.by, value: s.value, inputValue: '<PIN>', key: 'Enter' }); saveSteps(); }
      }
    }, true);
  }
  addListeners(document);
  for (var i = 0; i < window.frames.length; i++) {
    try { addListeners(window.frames[i].document); } catch (e) {}
  }
  var checkFrames = setInterval(function() {
    for (var i = 0; i < window.frames.length; i++) {
      try { addListeners(window.frames[i].document); } catch (e) {}
    }
  }, 500);
  window._bbRecorderCheck = checkFrames;
})();
"""


def _record_pincode_flow(driver) -> bool:
    """
    Record user's pincode flow: inject recorder (main doc + all iframes), user does flow, press Enter to save.
    Saves to pincode_flow.json. Returns True if steps were saved.
    """
    import threading
    try:
        from selenium.webdriver.common.by import By
    except ImportError:
        pass
    print("Opening BigBasket... Do your pincode flow: click location, type pincode, select area.")
    print("When done, press Enter HERE (in this terminal) to save the steps.")
    driver.get("https://www.bigbasket.com/")
    driver.maximize_window()
    time.sleep(5)
    try:
        driver.execute_script(_RECORD_PINCODE_JS)
    except Exception as e:
        print(f"Recorder inject failed: {e}", file=sys.stderr)
    done = threading.Event()
    latest_steps = []

    def live_count():
        while not done.is_set():
            done.wait(2)
            if done.is_set():
                break
            try:
                raw = driver.execute_script(
                    "var t = window.top; var arr = (t && t._bbRecordedSteps) ? t._bbRecordedSteps : []; "
                    "try { var s = t.sessionStorage.getItem('_bbRecordedSteps'); if (s) arr = JSON.parse(s); } catch(e) {} "
                    "return JSON.stringify(arr);"
                )
                if raw:
                    latest_steps[:] = json.loads(raw)
                    n = len(latest_steps)
                    if n > 0:
                        print(f"  Recorded {n} steps so far...")
            except Exception:
                pass
    t = threading.Thread(target=live_count, daemon=True)
    t.start()
    try:
        input()
    finally:
        done.set()
    steps = list(latest_steps) if latest_steps else []
    if not steps:
        try:
            raw = driver.execute_script(
                "var t = window.top; var arr = (t && t._bbRecordedSteps) ? t._bbRecordedSteps : []; "
                "try { var s = t.sessionStorage.getItem('_bbRecordedSteps'); if (s) arr = JSON.parse(s); } catch(e) {} "
                "return JSON.stringify(arr);"
            )
            if raw:
                steps = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception:
            pass
    if not steps:
        print("No steps recorded.", file=sys.stderr)
        print("Tip: The location widget may be in an iframe; we inject into all frames. Try clicking once on the page first, then open location and type pincode.", file=sys.stderr)
        return False
    # Dedupe: merge consecutive send_keys with same selector; keep selector (by, value) and inputValue
    steps_deduped = []
    for s in steps:
        if s.get("action") == "send_keys" and steps_deduped and steps_deduped[-1].get("action") == "send_keys":
            prev = steps_deduped[-1]
            if prev.get("by") == s.get("by") and (prev.get("value") == s.get("value") or s.get("value") == "<PIN>" or prev.get("value") == "<PIN>"):
                continue
        steps_deduped.append(s)
    save_json(PINCODE_FLOW_FILE, {"steps": steps_deduped})
    print(f"Saved {len(steps_deduped)} steps to pincode_flow.json. Future runs will use this to set pincode.")
    return True


def _find_element_any_frame(driver, by, value):
    """Find element in main document or any same-origin iframe. Returns (element, frame_index) or (None, -1)."""
    try:
        from selenium.webdriver.common.by import By
    except ImportError:
        return None, -1
    driver.switch_to.default_content()
    try:
        el = driver.find_element(by, value)
        if el.is_displayed():
            return el, 0
    except Exception:
        pass
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for idx in range(len(iframes)):
            driver.switch_to.default_content()
            driver.switch_to.frame(idx)
            try:
                el = driver.find_element(by, value)
                if el.is_displayed():
                    return el, idx + 1
            except Exception:
                pass
    except Exception:
        pass
    driver.switch_to.default_content()
    return None, -1


def _playback_pincode_flow(driver, pincode: str) -> bool:
    """
    Play back recorded steps from pincode_flow.json; substitute pincode for <PIN>.
    Opens location modal first if needed. Tries main document and iframes.
    """
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
    except ImportError:
        return False
    data = load_json(PINCODE_FLOW_FILE, None)
    if not data or not isinstance(data.get("steps"), list):
        return False
    steps = data["steps"]
    pin = (pincode or "").strip()

    # If first step is the search/location input, open the location modal first so it's visible
    first = steps[0] if steps else {}
    if first.get("action") == "click" and "placeholder" in str(first.get("value", "")):
        for xpath in [
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'select location')]",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'deliver to')]",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'change location')]",
        ]:
            try:
                el, _ = _find_element_any_frame(driver, By.XPATH, xpath)
                if el and el.is_displayed():
                    el.click()
                    time.sleep(2)
                    break
            except Exception:
                pass

    last_selector = None
    for i, s in enumerate(steps):
        action = s.get("action")
        by, val = s.get("by"), s.get("value")
        input_val = s.get("inputValue", val)

        if action == "send_keys" and (val == "<PIN>" or input_val == "<PIN>"):
            if val != "<PIN>" and by:
                last_selector = (by, val)
            if last_selector:
                by, val = last_selector[0], last_selector[1]
            elif not by or val == "<PIN>":
                if i > 0:
                    prev = steps[i - 1]
                    by, val = prev.get("by"), prev.get("value")
                if not by or val == "<PIN>":
                    continue
        elif by and val is not None and val != "<PIN>":
            last_selector = (by, val)

        if not by or val is None:
            continue
        try:
            if by == "id":
                el, _ = _find_element_any_frame(driver, By.ID, val)
            elif by == "xpath":
                el, _ = _find_element_any_frame(driver, By.XPATH, val)
            elif by == "css":
                el, _ = _find_element_any_frame(driver, By.CSS_SELECTOR, val)
            else:
                continue
            if el is None:
                continue
            if action == "click":
                el.click()
                time.sleep(0.8)
            elif action == "send_keys":
                if s.get("key") == "Enter":
                    el.send_keys(Keys.ENTER)
                else:
                    text = pin if (input_val == "<PIN>" or val == "<PIN>") else (input_val or val or "")
                    el.clear()
                    el.send_keys(text)
                time.sleep(1.2)
        except Exception as e:
            print(f"  (Playback step {i+1} failed: {e})", file=sys.stderr)
    driver.switch_to.default_content()
    time.sleep(2)
    return True


def _set_pincode_via_cookies(driver, pincode: str) -> bool:
    """
    Set pincode by writing BigBasket's location cookies directly (from places API lat/lng).
    Gets lat/lng via places autocomplete + details in browser, then sets _bb_pin_code,
    _bb_lat_long, _bb_addressinfo; refresh and verify.
    """
    pin = (pincode or "").strip()
    if not pin:
        return False
    # Get lat, lng, area, city from places API in browser (same domain/cookies)
    js_get_location = """
    var pin = arguments[0];
    var callback = arguments[arguments.length - 1];
    var token = Math.random().toString(36).slice(2, 34);
    fetch('https://www.bigbasket.com/places/v1/places/autocomplete/?inputText=' + encodeURIComponent(pin) + '&token=' + token, { credentials: 'include' })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var preds = data.predictions || data.results || data.places || [];
        if (!preds.length) { callback(null); return; }
        var first = preds[0];
        var placeId = first.place_id || first.id || first.placeId;
        var area = (first.description || first.formatted_address || '').trim();
        if (!placeId) { callback(null); return; }
        return fetch('https://www.bigbasket.com/places/v1/places/details/?placeId=' + placeId + '&token=' + Math.random().toString(36).slice(2, 34), { credentials: 'include' })
            .then(function(r) { return r && r.json ? r.json() : null; })
            .then(function(details) {
                if (!details) { callback(null); return; }
                var lat = details.lat || details.latitude;
                var lng = details.lng || details.longitude;
                if (lat == null && details.geometry && details.geometry.location) {
                    lat = details.geometry.location.lat;
                    lng = details.geometry.location.lng;
                }
                if (lng == null && details.geometry) lng = details.geometry.location && details.geometry.location.lng;
                if (lat == null || lng == null) { callback(null); return; }
                var city = (details.locality || details.city || (details.address_components && details.address_components[0] && details.address_components[0].long_name) || '').trim();
                if (!area && details.formatted_address) area = details.formatted_address;
                callback({ lat: lat, lng: lng, area: area || '', city: city || '' });
            });
    })
    .catch(function() { callback(null); });
    """
    try:
        loc = driver.execute_async_script(js_get_location, pin)
        if not loc or not isinstance(loc, dict) or loc.get("lat") is None or loc.get("lng") is None:
            return False
        lat = loc["lat"]
        lng = loc["lng"]
        area = (loc.get("area") or "").strip() or pin
        city = (loc.get("city") or "").strip()
        # Cookie formats from recorded session: _bb_pin_code plain, _bb_lat_long base64(lat|lng), _bb_addressinfo base64(lat|lng|area|pincode|city|1|false|true|true|Bigbasketeer)
        lat_lng_str = f"{lat}|{lng}"
        addr_parts = [lat_lng_str, area, pin, city, "1", "false", "true", "true", "Bigbasketeer"]
        addr_str = "|".join(addr_parts)
        lat_long_b64 = base64.b64encode(lat_lng_str.encode("utf-8")).decode("ascii")
        addr_b64 = base64.b64encode(addr_str.encode("utf-8")).decode("ascii")
        domain = ".bigbasket.com"
        # Must be on domain to add cookies
        if "bigbasket.com" not in (driver.current_url or ""):
            driver.get("https://www.bigbasket.com/")
            time.sleep(1)
        for name, value, secure in [
            ("_bb_pin_code", pin, False),
            ("_bb_lat_long", lat_long_b64, True),
            ("_bb_addressinfo", addr_b64, False),
        ]:
            try:
                driver.add_cookie({
                    "name": name,
                    "value": value,
                    "path": "/",
                    "domain": domain,
                    "secure": secure,
                    "sameSite": "Lax",
                })
            except Exception as e:
                print(f"  (Cookie {name} failed: {e})", file=sys.stderr)
                return False
        time.sleep(0.5)
        driver.refresh()
        time.sleep(3)
        # Verify pincode appears on page
        try:
            body = driver.find_element("tag name", "body").text
            if pin in body:
                return True
            if pin in (driver.page_source or ""):
                return True
        except Exception:
            pass
        return False
    except Exception as e:
        print(f"  (Set pincode via cookies failed: {e})", file=sys.stderr)
    return False


def _set_pincode_via_api_in_browser(driver, pincode: str) -> bool:
    """
    Set pincode by calling BigBasket's places API from the browser (same flow as the site).
    Uses the page's cookies so location cookies get set; then refresh. No UI automation.
    """
    pin = (pincode or "").strip()
    if not pin:
        return False
    js = """
    var pin = arguments[0];
    var callback = arguments[arguments.length - 1];
    var token = Math.random().toString(36).slice(2, 34);
    fetch('https://www.bigbasket.com/places/v1/places/autocomplete/?inputText=' + encodeURIComponent(pin) + '&token=' + token, { credentials: 'include' })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var preds = data.predictions || data.results || data.places || [];
        if (!preds.length) { callback(false); return; }
        var first = preds[0];
        var placeId = first.place_id || first.id || first.placeId;
        if (!placeId) { callback(false); return; }
        return fetch('https://www.bigbasket.com/places/v1/places/details/?placeId=' + placeId + '&token=' + Math.random().toString(36).slice(2, 34), { credentials: 'include' });
    })
    .then(function(r) { return r && r.json ? r.json() : null; })
    .then(function(details) {
        if (!details) { callback(false); return; }
        var lat = details.lat || details.latitude;
        var lng = details.lng || details.longitude;
        if (lat == null && details.geometry && details.geometry.location) {
            lat = details.geometry.location.lat;
            lng = details.geometry.location.lng;
        }
        if (lng == null && details.geometry) lng = details.geometry.location && details.geometry.location.lng;
        if (lat == null || lng == null) { callback(false); return; }
        return fetch('https://www.bigbasket.com/ui-svc/v1/serviceable/?lat=' + lat + '&lng=' + lng + '&send_all_serviceability=true', { credentials: 'include' });
    })
    .then(function(r) { return r && r.ok; })
    .then(function(ok) { callback(ok === true); })
    .catch(function() { callback(false); });
    """
    try:
        result = driver.execute_async_script(js, pin)
        if result is True:
            time.sleep(1)
            driver.refresh()
            time.sleep(3)
            # Verify pincode actually appears on page (API can return 200 but UI not update)
            try:
                body = driver.find_element("tag name", "body").text
                if pin in body:
                    return True
                # Some UIs show area name; check for common location text that implies pincode was set
                page_src = driver.page_source or ""
                if pin in page_src:
                    return True
            except Exception:
                pass
            # API said OK but pincode not visible on page
            return False
    except Exception as e:
        print(f"  (API pincode failed: {e})", file=sys.stderr)
    return False


def _set_pincode_heuristic(driver, pincode: str) -> bool:
    """
    Set pincode using flexible selectors and main + all iframes. More reliable than recorded XPaths.
    """
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.keys import Keys
    except ImportError:
        return False
    pin = (pincode or "").strip()
    if not pin:
        return False
    wait = WebDriverWait(driver, 15)
    def _click_location_opener():
        # When no location: "Select Location" / "Deliver to". When location set: "122001, Gurgaon" / "Delivery in 8 mins"
        for xpath in [
            "//header//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'select location')]",
            "//header//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'deliver to')]",
            "//header//*[contains(., 'Delivery in') or contains(., '122001') or contains(., 'Gurgaon')]",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'select location')]",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'deliver to')]",
            "//*[contains(., 'Delivery in')]",
            "//*[contains(., '122001') and string-length(normalize-space(.)) < 30]",
        ]:
            try:
                el, _ = _find_element_any_frame(driver, By.XPATH, xpath)
                if el and el.is_displayed():
                    try:
                        el.click()
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].click();", el)
                        except Exception:
                            pass
                    return True
            except Exception:
                pass
        return False

    def _find_input():
        input_xpaths = [
            "//input[contains(@placeholder, 'Search for area') or contains(@placeholder, 'area or street')]",
            "//input[contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'pincode')]",
            "//input[contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'area')]",
            "//input[contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'location')]",
        ]
        for xpath in input_xpaths:
            el, _ = _find_element_any_frame(driver, By.XPATH, xpath)
            if el and el.is_displayed():
                return el
        return None

    def _click_first_suggestion():
        for xpath in [
            "//ul//li[.//span or .//div][1]",
            "//li[contains(@class,'suggestion') or contains(@class,'option') or contains(@class,'item')]",
            "//*[@role='option']",
            "//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]",
        ]:
            try:
                el, _ = _find_element_any_frame(driver, By.XPATH, xpath)
                if el and el.is_displayed():
                    el.click()
                    return True
            except Exception:
                pass
        return False

    try:
        driver.switch_to.default_content()
        time.sleep(2)
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(., 'Delivery') or contains(., 'Select') or contains(., 'Deliver')]")))
        except Exception:
            pass
        print("  Clicking location (Select Location / Deliver to / 122001)...")
        if not _click_location_opener():
            print("  Could not find or click location opener.", file=sys.stderr)
            return False
        time.sleep(4)
        inp = None
        for _ in range(8):
            inp = _find_input()
            if inp:
                break
            time.sleep(1)
        if not inp:
            print("  Location modal did not open or pincode input not found.", file=sys.stderr)
            return False
        print("  Typing pincode...")
        inp.clear()
        inp.send_keys(pin)
        time.sleep(2)
        try:
            inp.send_keys(Keys.ARROW_DOWN)
            time.sleep(0.3)
            inp.send_keys(Keys.ENTER)
        except Exception:
            pass
        time.sleep(1.5)
        print("  Selecting first suggestion...")
        _click_first_suggestion()
        time.sleep(2)
        driver.switch_to.default_content()
        if "/choose-city" in driver.current_url:
            driver.get("https://www.bigbasket.com/")
            time.sleep(2)
        print("  Pincode set.")
        return True
    except Exception as e:
        print(f"  Heuristic pincode failed: {e}", file=sys.stderr)
        driver.switch_to.default_content()
        return False


def _set_pincode_in_browser(driver, pincode: str) -> bool:
    """
    Set delivery pincode: try cookies first (set _bb_pin_code, _bb_lat_long, _bb_addressinfo),
    then API (serviceable), then heuristic, then playback.
    Returns True if pincode was set, False otherwise.
    """
    pin = (pincode or "").strip()
    if not pin:
        return False

    print("Setting pincode (cookies)...")
    if _set_pincode_via_cookies(driver, pin):
        print("Pincode set via cookies.")
        return True
    print("Setting pincode (API)...")
    if _set_pincode_via_api_in_browser(driver, pin):
        print("Pincode set via API.")
        return True
    print("API did not update location (or verification failed); trying UI...")
    print("Setting pincode (heuristic)...")
    if _set_pincode_heuristic(driver, pin):
        return True
    if PINCODE_FLOW_FILE.exists():
        print("Trying recorded flow (pincode_flow.json)...")
        _playback_pincode_flow(driver, pin)
        time.sleep(2)
        return True
    return False


def run_with_browser(product_urls: list[str], pincodes: list[str], config: dict | None = None) -> None:
    """
    Check stock using a real Chrome window (like deepakksahu/bigbasket_slot_notifier).
    For each pincode: set location via cookies, then check every product (API then page fallback).
    """
    # BigBasket blocks headless Chrome. Use minimized (real window, minimized) instead of headless.
    headless = bool(config.get("headless", False)) if config else False
    minimized = bool(config.get("minimized", False)) if config else False
    driver = _get_driver(headless=headless)
    if not driver:
        sys.exit(1)
    if minimized and not headless:
        try:
            driver.minimize_window()
        except Exception:
            pass
    # Dedupe pincodes, keep order
    seen = set()
    pincode_list = []
    for p in (pincodes or []):
        pin = (p or "").strip()
        if pin and pin not in seen:
            seen.add(pin)
            pincode_list.append(pin)
    if not pincode_list:
        pincode_list = ["browser"]
    state = load_json(STATE_FILE, {})
    changes = []
    if config is None:
        config = load_json(CONFIG_FILE, {})

    try:
        print("Opening BigBasket in Chrome...")
        driver.get("https://www.bigbasket.com/")
        if minimized and not headless:
            try:
                driver.minimize_window()
            except Exception:
                pass
        else:
            driver.maximize_window()
        time.sleep(2)
        build_id = get_build_id_from_html(driver.page_source or "")
        if not build_id:
            build_id = "TiBvbC2dBTBqbHRDcdku3"
        use_api = config.get("check_stock_via_api", True)

        for pin in pincode_list:
            # Clear cookies and inject fresh cookies on every pincode change
            try:
                driver.delete_all_cookies()
            except Exception:
                pass
            driver.get("https://www.bigbasket.com/")
            time.sleep(2)
            if PINCODE_SESSION_RECORD_FILE.exists():
                try:
                    rec = load_json(PINCODE_SESSION_RECORD_FILE, None)
                    cookies = rec.get("cookies") if isinstance(rec, dict) else []
                    for c in cookies:
                        try:
                            driver.add_cookie(c)
                        except Exception:
                            pass
                    driver.refresh()
                    time.sleep(2)
                    print("Applied cookies from pincode_session_record.json")
                except Exception:
                    pass

            if pin == "browser":
                print("Set your delivery pincode in the browser, then press Enter here...")
                input()
            elif config.get("auto_pincode", True):
                print(f"Setting delivery pincode to {pin}...")
                if _set_pincode_in_browser(driver, pin):
                    print("Pincode set.")
                else:
                    print("Auto pincode failed. Set pincode in the browser, then press Enter here...")
                    input()
            else:
                print(f"Set delivery pincode to {pin} in the browser, then press Enter here...")
                input()

            print(f"--- Pincode {pin} ---")
            for url in product_urls:
                url = url.strip()
                if not url or url.startswith("#"):
                    continue
                pid, slug = parse_product_url(url)
                if not pid or not slug:
                    print(f"  Skip (invalid URL): {url[:50]}...")
                    continue

                print(f"  Checking: {slug.replace('-', ' ').title()}...")
                result_status, result_title, error_detail = None, None, "Check failed"
                if use_api and build_id:
                    result_status, result_title = check_one_via_api_in_browser(driver, pid, slug, build_id)
                if result_status is None or result_status == "unknown":
                    driver.get(url)
                    time.sleep(3)
                    html = driver.page_source
                    if not html or "Access Denied" in html:
                        result_status, result_title = "error", slug.replace("-", " ").title()
                        error_detail = "Access Denied or page failed"
                    else:
                        result_status, result_title = parse_stock_from_html(html)
                        if not result_title:
                            result_title = slug.replace("-", " ").title()
                else:
                    if not result_title:
                        result_title = slug.replace("-", " ").title()
                if result_status and result_status != "error":
                    print(f"  {result_title or slug.replace('-', ' ').title()}: {result_status.upper()}")
                elif result_status == "error":
                    print(f"  {result_title or slug.replace('-', ' ').title()}: ERROR")
                    _send_telegram_error(config, result_title or slug.replace("-", " ").title(), pin, url, error_detail)

                key = f"{pid}|{pin}"
                prev = state.get(key, {})
                state[key] = {
                    "url": url,
                    "slug": slug,
                    "title": result_title if result_status != "error" else slug.replace("-", " ").title(),
                    "status": result_status,
                    "pincode": pin,
                }
                if prev.get("status") and result_status != prev["status"]:
                    changes.append({
                        "title": result_title if result_status != "error" else slug.replace("-", " ").title(),
                        "pincode": pin,
                        "from": prev["status"],
                        "to": result_status,
                        "url": url,
                    })
                    if result_status == "in_stock":
                        print(f"  [BACK IN STOCK] {result_title}")
                # Each product if in_stock: send one Telegram message (with screenshot when enabled)
                if result_status == "in_stock":
                    title_display = result_title if result_status != "error" else slug.replace("-", " ").title()
                    caption = f"BigBasket: {title_display} is in stock @ pincode {pin}\n\n{url}"
                    if config.get("telegram_send_screenshot", True):
                        try:
                            if pid not in (driver.current_url or ""):
                                driver.get(url)
                                time.sleep(2)
                            screenshot_bytes = driver.get_screenshot_as_png()
                            if screenshot_bytes:
                                _send_telegram_photo(config, screenshot_bytes, caption)
                            else:
                                _send_telegram_in_stock(config, {"title": title_display, "pincode": pin, "url": url, "to": "in_stock"})
                        except Exception as e:
                            print(f"  (Screenshot failed: {e}, sending text only)", file=sys.stderr)
                            _send_telegram_in_stock(config, {"title": title_display, "pincode": pin, "url": url, "to": "in_stock"})
                    else:
                        _send_telegram_in_stock(config, {"title": title_display, "pincode": pin, "url": url, "to": "in_stock"})
                time.sleep(2)

        save_json(STATE_FILE, state)
        if changes:
            print("--- Changes ---")
            for c in changes:
                print(f"  {c['title']} (@ {c['pincode']}): {c['from']} -> {c['to']}")
            in_stock_changes = [c for c in changes if c.get("to") == "in_stock"]
            if in_stock_changes and not config.get("telegram_send_screenshot", True):
                print(f"Sending Telegram for {len(in_stock_changes)} in_stock alert(s)...")
                for c in in_stock_changes:
                    _send_telegram_in_stock(config, c)
    finally:
        driver.quit()


def run(product_urls: list[str], pincodes: list[str], session_file: str | Path | None = None, config: dict | None = None) -> None:
    """
    Check stock for each product × pincode. Save state, print results and changes.
    If session_file is set, use headers from that file (real user session) for all requests
    and skip the pincode API (inspired by shatadru/big_basket_automation).
    """
    if config is None:
        config = load_json(CONFIG_FILE, {})
    state = load_json(STATE_FILE, {})
    changes = []

    shared_session = None
    if session_file:
        path = Path(session_file) if not isinstance(session_file, Path) else session_file
        if not path.is_absolute():
            path = BASE / path
        loaded = load_session_from_file(path)
        if loaded:
            shared_session = requests.Session()
            shared_session.headers.update(HEADERS)
            shared_session.headers.update(loaded)
            print("Using session from file (real user session).")
        else:
            print("Could not load session file; falling back to pincode API.", file=sys.stderr)

    for pincode in pincodes:
        pin = pincode.strip()
        if not pin:
            continue
        print(f"Pincode: {pin}")

        if shared_session:
            session = shared_session
        else:
            session = set_pincode_session(pin)
            if not session:
                print("  (Could not set pincode via API; continuing anyway.)")
                session = requests.Session()
                session.headers.update(HEADERS)

        for url in product_urls:
            url = url.strip()
            if not url or url.startswith("#"):
                continue

            result = check_one(url, pin, session)
            pid = result.get("product_id") or result["url"]
            key = f"{pid}|{pin}"
            prev = state.get(key, {})
            state[key] = {
                "url": result["url"],
                "slug": result.get("slug"),
                "title": result.get("title"),
                "status": result["status"],
                "pincode": pin,
            }

            if result["status"] == "error":
                _send_telegram_error(config, result.get("title") or result.get("slug") or pid, pin, result["url"], result.get("error") or "Check failed")
            if prev.get("status") and result["status"] != prev["status"]:
                changes.append({
                    "title": result.get("title") or result.get("slug") or pid,
                    "pincode": pin,
                    "from": prev["status"],
                    "to": result["status"],
                    "url": result["url"],
                })
                if result["status"] == "in_stock":
                    print(f"  [BACK IN STOCK] {result.get('title') or result.get('slug')}")

            label = result["status"].upper() if result["status"] != "error" else (result.get("error") or "ERROR")
            print(f"  {result.get('title') or result.get('slug') or pid}: {label}")

            time.sleep(8)

        print()

    save_json(STATE_FILE, state)

    if changes:
        print("--- Changes ---")
        for c in changes:
            print(f"  {c['title']} (@ {c['pincode']}): {c['from']} -> {c['to']}")
        in_stock_changes = [c for c in changes if c.get("to") == "in_stock"]
        if in_stock_changes:
            print(f"Sending Telegram for {len(in_stock_changes)} in_stock alert(s)...")
            for c in in_stock_changes:
                _send_telegram_in_stock(config, c)


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="BigBasket stock checker by pincode")
    parser.add_argument("urls", nargs="*", help="Product URLs (optional if using -c)")
    parser.add_argument("-c", "--config", action="store_true", help="Use config.json")
    parser.add_argument("-f", "--config-file", help="Path to config JSON (overrides config.json)")
    parser.add_argument("-p", "--pincode", help="Pincode(s), comma-separated (overrides config)")
    parser.add_argument("-b", "--browser", action="store_true", help="Use Chrome (set pincode in browser; no Access Denied)")
    parser.add_argument("--headless", action="store_true", help="Run Chrome headless (no window)")
    parser.add_argument("--record-pincode", action="store_true", help="Record your manual pincode flow; save to pincode_flow.json for auto playback")
    parser.add_argument("--test-telegram", action="store_true", help="Send one test Telegram message and exit (verify bot/chat/topic)")
    parser.add_argument("--loop", type=float, default=0, metavar="MINUTES", help="Run every N minutes (e.g. 5)")
    args = parser.parse_args()

    config_path = CONFIG_FILE
    if args.config_file:
        config_path = Path(args.config_file)
        if not config_path.is_absolute():
            config_path = BASE / config_path
    config = load_json(config_path, {})
    if args.test_telegram:
        print("Sending test Telegram message...")
        ok = _send_telegram(config, "Test from BigBasket tracker – if you see this, alerts are working.", silent_if_missing=False)
        print("Done." if ok else "Failed (check token, chat_id, topic_id in config).")
        return
    urls = list(args.urls) if args.urls else (config.get("product_urls") or config.get("urls") or [])
    if args.config or not urls:
        urls = config.get("product_urls") or config.get("urls") or []
    urls = [u.strip() for u in urls if u and isinstance(u, str) and u.strip() and not u.strip().startswith("#")]

    use_browser = args.browser or config.get("use_browser")

    if args.pincode:
        pincodes = [p.strip() for p in args.pincode.split(",") if p.strip()]
    else:
        raw = config.get("pincodes") or config.get("pincode") or config.get("pin_code")
        if isinstance(raw, list):
            pincodes = [str(x).strip() for x in raw if str(x).strip()]
        elif raw:
            pincodes = [str(raw).strip()]
        else:
            pincodes = []

    if args.record_pincode:
        driver = _get_driver()
        if driver:
            try:
                _record_pincode_flow(driver)
            finally:
                driver.quit()
        return

    if not urls:
        print("No product URLs. Add product_urls in config.json or pass URLs.", file=sys.stderr)
        sys.exit(1)
    loop_minutes = max(0, float(args.loop or 0))
    if use_browser:
        if not pincodes:
            pincodes = ["browser"]
        if args.headless:
            config = {**(config or {}), "headless": True}
        while True:
            run_with_browser(urls, pincodes, config=config)
            if loop_minutes <= 0:
                break
            print(f"Sleeping {loop_minutes} minutes...")
            time.sleep(loop_minutes * 60)
    else:
        if not pincodes:
            print("No pincodes. Add pincodes in config.json or use -p.", file=sys.stderr)
            sys.exit(1)
        session_file = config.get("session_file")
        while True:
            run(urls, pincodes, session_file=session_file, config=config)
            if loop_minutes <= 0:
                break
            print(f"Sleeping {loop_minutes} minutes...")
            time.sleep(loop_minutes * 60)


if __name__ == "__main__":
    main()
