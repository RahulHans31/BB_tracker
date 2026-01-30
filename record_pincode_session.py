"""
Record everything while you set the pincode on BigBasket: UI steps, network calls, cookies.
Then verify that the recorded session can set the pincode.

Usage:
  python record_pincode_session.py              # Record: do your pincode flow, press Enter to save
  python record_pincode_session.py --verify     # Verify: load record, set pincode via API, check page
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
RECORD_FILE = BASE / "pincode_session_record.json"

# Same recorder JS as tracker (clicks + inputs, save to sessionStorage)
RECORD_JS = """
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
  function saveSteps() {
    try { top.sessionStorage.setItem('_bbRecordedSteps', JSON.stringify(top._bbRecordedSteps)); } catch (e) {}
  }
  function addListeners(doc) {
    if (!doc || doc._bbRecorderInjected) return;
    doc._bbRecorderInjected = true;
    function pushClick(e) {
      var s = getSelector(e.target);
      if (s) { top._bbRecordedSteps.push({ action: 'click', by: s.by, value: s.value }); saveSteps(); }
    }
    function pushInput(e) {
      var s = getSelector(e.target);
      if (s && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA'))
        top._bbRecordedSteps.push({ action: 'send_keys', by: s.by, value: s.value, inputValue: '<PIN>' }); saveSteps();
    }
    function pushEnter(e) {
      if (e.key === 'Enter') {
        var s = getSelector(e.target);
        if (s) { top._bbRecordedSteps.push({ action: 'send_keys', by: s.by, value: s.value, inputValue: '<PIN>', key: 'Enter' }); saveSteps(); }
      }
    }
    doc.addEventListener('click', pushClick, true);
    doc.addEventListener('input', pushInput, true);
    doc.addEventListener('keydown', pushEnter, true);
  }
  addListeners(document);
  for (var i = 0; i < window.frames.length; i++) {
    try { addListeners(window.frames[i].document); } catch (e) {}
  }
  setInterval(function() {
    for (var i = 0; i < window.frames.length; i++) {
      try { addListeners(window.frames[i].document); } catch (e) {}
    }
  }, 500);
})();
"""


def get_driver(enable_performance_log=True):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("Need: pip install selenium webdriver-manager", file=sys.stderr)
        return None
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    if enable_performance_log:
        opts.set_capability("goog:loggingPrefs", {"performance": "ALL", "browser": "ALL"})
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    except Exception as e:
        print(f"Chrome start failed: {e}", file=sys.stderr)
        return None


def parse_performance_log(driver):
    """Extract network requests/responses from Chrome performance log."""
    try:
        logs = driver.get_log("performance")
    except Exception:
        return []
    network_events = []
    for entry in logs:
        try:
            msg = json.loads(entry["message"])["message"]
            method = msg.get("method", "")
            if "Network.requestWillBeSent" in method:
                params = msg.get("params", {})
                req = params.get("request", {})
                network_events.append({
                    "type": "request",
                    "url": req.get("url", ""),
                    "method": req.get("method", "GET"),
                    "requestId": params.get("requestId"),
                })
            elif "Network.responseReceived" in method:
                params = msg.get("params", {})
                res = params.get("response", {})
                network_events.append({
                    "type": "response",
                    "url": res.get("url", ""),
                    "status": res.get("status"),
                    "requestId": params.get("requestId"),
                })
        except (json.JSONDecodeError, KeyError):
            continue
    return network_events


def record_session(pincode_hint: str = "122001"):
    print("Opening BigBasket in Chrome...")
    driver = get_driver(enable_performance_log=True)
    if not driver:
        return False
    try:
        driver.get("https://www.bigbasket.com/")
        driver.maximize_window()
        time.sleep(4)
        driver.execute_script(RECORD_JS)
        print("Recording: UI steps, network, and cookies.")
        print(f"Do your pincode flow (e.g. set pincode to {pincode_hint}).")
        print("When done, press Enter HERE to save the session...")
        input()

        # Collect UI steps (from our script + sessionStorage backup)
        steps = []
        try:
            steps = driver.execute_script(
                "var t = window.top; var arr = (t && t._bbRecordedSteps) ? t._bbRecordedSteps : []; "
                "try { var s = t.sessionStorage.getItem('_bbRecordedSteps'); if (s) arr = JSON.parse(s); } catch(e) {} "
                "return arr;"
            )
        except Exception:
            pass
        if not steps and isinstance(steps, list):
            steps = []

        # Dedupe consecutive send_keys same selector
        steps_deduped = []
        for s in steps:
            if s.get("action") == "send_keys" and steps_deduped and steps_deduped[-1].get("action") == "send_keys":
                prev = steps_deduped[-1]
                if prev.get("by") == s.get("by") and (prev.get("value") == s.get("value") or s.get("value") == "<PIN>" or prev.get("value") == "<PIN>"):
                    continue
            steps_deduped.append(s)

        # Network log
        network = parse_performance_log(driver)
        # Filter to BigBasket API calls that matter for location
        location_apis = [e for e in network if "bigbasket.com" in e.get("url", "") and (
            "places/" in e.get("url", "") or "ui-svc" in e.get("url", "") or "serviceable" in e.get("url", "")
        )]

        # Cookies
        cookies = driver.get_cookies()

        record = {
            "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "page_url": driver.current_url,
            "cookies": cookies,
            "ui_steps": steps_deduped,
            "network_all_count": len(network),
            "network_location_apis": location_apis,
            "network_sample": network[:50],
        }
        with open(RECORD_FILE, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        print(f"Saved to {RECORD_FILE}:")
        print(f"  - {len(cookies)} cookies")
        print(f"  - {len(steps_deduped)} UI steps")
        print(f"  - {len(network)} network events ({len(location_apis)} location-related API calls)")
        return True
    finally:
        driver.quit()


def verify_session(pincode: str):
    """Load recorded session, open browser, add cookies, set pincode via API, check page."""
    if not RECORD_FILE.exists():
        print(f"No record found at {RECORD_FILE}. Run without --verify first.", file=sys.stderr)
        return False
    with open(RECORD_FILE, encoding="utf-8") as f:
        record = json.load(f)
    cookies = record.get("cookies", [])
    pin = (pincode or "").strip()
    if not pin:
        pin = "122001"

    print("Verify: opening browser, applying recorded cookies, setting pincode via API...")
    driver = get_driver(enable_performance_log=False)
    if not driver:
        return False
    try:
        driver.get("https://www.bigbasket.com/")
        time.sleep(2)
        for c in cookies:
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        driver.refresh()
        time.sleep(3)

        # Set pincode via API (same as tracker)
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
        except Exception as e:
            print(f"  API call failed: {e}", file=sys.stderr)
            result = False
        if not result:
            print("  Pincode API returned false. Check console.", file=sys.stderr)
            time.sleep(5)
            driver.quit()
            return False
        time.sleep(1)
        driver.refresh()
        time.sleep(4)
        html = driver.page_source
        if pin in html and ("Gurgaon" in html or "Delivery" in html):
            print("  OK: Pincode appears on page after API call.")
        else:
            print("  Page may not show pincode yet; check browser.", file=sys.stderr)
        print("  Leaving browser open 10 sec for you to check...")
        time.sleep(10)
        return True
    finally:
        driver.quit()


def main():
    ap = argparse.ArgumentParser(description="Record pincode session (UI, network, cookies) and optionally verify")
    ap.add_argument("--verify", action="store_true", help="Verify: load record, set pincode via API, check")
    ap.add_argument("--pincode", default="122001", help="Pincode for verify (default 122001)")
    args = ap.parse_args()

    if args.verify:
        verify_session(args.pincode)
    else:
        record_session(pincode_hint=args.pincode)


if __name__ == "__main__":
    main()
