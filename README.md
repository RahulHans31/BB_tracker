# BigBasket Stock Tracker

Check stock for BigBasket products at specific pincodes.

**Recommended: browser mode** (like [deepakksahu/bigbasket_slot_notifier](https://github.com/deepakksahu/bigbasket_slot_notifier)) – opens real Chrome; you set pincode once in the browser, then the script checks each product. No Access Denied.

## What it does

1. **Browser mode** (default) – Opens Chrome, you set delivery pincode on bigbasket.com (no login), press Enter; script visits each product URL and parses stock. Works reliably.
2. **Requests mode** – Uses session file (HAR/cURL) or pincode API; may get Access Denied on some networks.
3. **Parse stock** – Reads `__NEXT_DATA__` or “Add to basket” / “Notify Me” to get in_stock / out_of_stock.
4. **Save state** – Stores last status per product per pincode in `state.json` and prints changes (e.g. back in stock).

## Setup

```bash
pip install -r requirements.txt
```

## Config

Edit `config.json`:

```json
{
  "pincodes": ["122001"],
  "use_browser": true,
  "product_urls": [
    "https://www.bigbasket.com/pd/10000074/fresho-cauliflower-1-pc/",
    "https://www.bigbasket.com/pd/40300424/super-saver-sona-masoori-raw-rice-26-kg-bag/"
  ]
}
```

- **`use_browser`** (default: true) – Use real Chrome (like deepakksahu/bigbasket_slot_notifier). Set pincode once in the browser; no Access Denied. Requires Chrome and `pip install selenium webdriver-manager`.
- **`headless`** (default: false) – If true, Chrome runs without a window. **BigBasket often blocks headless Chrome** (Access Denied). Prefer **`minimized`** instead.
- **`minimized`** (default: false) – If true, Chrome runs with a real window but **minimized** (taskbar only). Use for cron/VMs so BigBasket doesn’t block; override from CLI with `--headless` only if you know it works for you.
- **`auto_pincode`** (default: false) – If true, script tries to set pincode automatically (heuristic + recorded flow). If false, Chrome opens and you set pincode manually, then press Enter (most reliable).
- **Telegram in-stock alerts** – Set `telegram_bot_token`, `telegram_chat_id`, and optionally `telegram_topic_id` (for forum topics) in config. When a product goes **in_stock**, the script sends a message to that chat/topic.
- **Telegram error alerts** – Set `telegram_error_chat_id` (e.g. `7992845749`) in config. When any product check **fails** (Access Denied, check failed, etc.), the script sends an error message to that chat.
- **Telegram “in stock” summary** – Set `telegram_alert_when_any_in_stock`: true in config. At the end of each run, if any product is in stock (for any pincode), the script sends **one** summary message listing them (no screenshot).
- **Telegram in-stock + screenshot** – For each product that is **in stock**, the script sends **one** Telegram message with a **screenshot** of the product page (Selenium). Set `telegram_send_screenshot`: true in config (default). Messages are sent during the run, one per product per pincode.
- **Run every N minutes** – Use `--loop 5` to run the check every 5 minutes (e.g. `python tracker.py -c -b --loop 5`).
- **`session_file`** (optional) – For requests mode only. Path to HAR, cURL paste, or plain headers. See **Session file** below.

## Run

```bash
# Install (includes Selenium + webdriver-manager for browser mode)
pip install -r requirements.txt

# Use config (browser mode if use_browser: true in config)
python tracker.py -c

# Force browser mode from command line
python tracker.py -c --browser

# Use a different config file (e.g. iPhone 15/16 128GB × pincodes; minimized window)
python tracker.py -f iphone_config.json -b

# Requests mode (no browser): set use_browser: false and optionally session_file
python tracker.py -c -p 122001 "https://www.bigbasket.com/pd/10000074/fresho-cauliflower-1-pc/"
```

**Multiple pincodes:** In browser mode the script loops over every pincode in config: for each pincode it sets location (cookies), then checks every product. So you get stock for each product × each pincode (e.g. iPhone 15/16 on 110016, 110045, 122001, etc.).

**Browser mode:** Chrome opens; the script sets your delivery pincode from config automatically. If you have recorded a flow (see **Record pincode flow** below), it replays that; otherwise it tries heuristic UI or asks you to set it manually. Then the script checks each product URL and prints IN_STOCK / OUT_OF_STOCK.

**Loading cookies (`pincode_session_record.json`):** Not required. The script sets pincode via BigBasket’s places API and writes `_bb_pin_code`, `_bb_lat_long`, `_bb_addressinfo` in the browser. If you have a recorded session file, the script applies those cookies first (can help on strict networks); if you don’t, it still works.

**Record pincode flow (recommended):** Run once to record your manual steps so future runs are fully automatic:

```bash
python tracker.py --record-pincode
```

Chrome opens. Do your usual pincode flow: click location, type pincode, select area. When done, press **Enter in the terminal**. The steps are saved to `pincode_flow.json`. Next runs with `python tracker.py -c` will replay this flow with the pincode from config.

## Schedule on VM

Run every 30–60 minutes so you don’t hit the site too often:

```bash
# cron example (every 45 min)
*/45 * * * * cd /path/to/BB_Trackler && python tracker.py -c -b
```

## Run with iPhone config (loop every 5 min + screenshots)

Use `iphone_config.json` for iPhone 15/16 128GB and your pincodes. Fill in `telegram_bot_token` and `telegram_chat_id` in that file.

```bash
python tracker.py -f iphone_config.json -b --loop 5
```

## Migrate to a VM or another machine

1. **Copy the project** – Copy the whole `BB_Trackler` folder to the VM. You need: `tracker.py`, `config.json` and/or `iphone_config.json`, `requirements.txt`. Optional: `pincode_session_record.json`, `pincode_flow.json`.

2. **On the VM: install Python 3 and Chrome** – Python 3.10+ and pip; Google Chrome (required for Selenium). Example (Ubuntu): `sudo apt install -y python3 python3-pip` then install Chrome, then `pip install -r requirements.txt`.

3. **Run once to confirm** – `python tracker.py -c -b --test-telegram`. If the test Telegram arrives, config is fine.

4. **Run in a loop (every 5 min)** – `python tracker.py -f iphone_config.json -b --loop 5`. Leave running in a terminal, or use `screen` / `tmux` so it keeps running after you disconnect.

5. **Optional: cron instead of --loop** – `*/5 * * * * cd /path/to/BB_Trackler && python tracker.py -f iphone_config.json -b`. Use `minimized`: true in config so Chrome runs minimized (BigBasket often blocks headless).

6. **Secrets** – Do not commit config files with real tokens to a public repo. On the VM, create config there and paste your token/chat_id.

## Inspiration / references

This tracker draws on three open-source projects:

- **[shatadru/big_basket_automation](https://github.com/shatadru/big_basket_automation)** – Session file approach: export cookies/headers from a logged-in browser (e.g. cURL), use them in `requests` for slot/availability checks. We use the same idea for stock checks and session-file parsing.
- **[deepakksahu/bigbasket_slot_notifier](https://github.com/deepakksahu/bigbasket_slot_notifier)** – Same goal (notify when something becomes available). Uses Selenium and a live browser; we added **browser mode** the same way (Chrome, set pincode once, then check).
- **[Gaurang105/BigBasket_Scraper](https://github.com/Gaurang105/BigBasket_Scraper)** – BigBasket scraping (products, Excel, Google Sheets). Useful reference for how the site is structured and how to work with its pages/APIs.

## Session file (if you get Access Denied)

You don’t need to log in. On BigBasket you can set pincode and check stock without an account—same in Chrome. The script tries to do the same via the pincode API, but BigBasket’s CDN often blocks plain `requests` (no browser fingerprint). So we reuse Chrome’s cookies/headers: the site then treats the script like your browser.

1. **In Chrome**: Open [bigbasket.com](https://www.bigbasket.com), set your delivery pincode (no login).
2. **Export the session** (any one of these):
   - **HAR**: DevTools (F12) → Network → right‑click the request list → “Save all as HAR with content”. Save as e.g. `session.har`. In `config.json` set `"session_file": "session.har"`. The script uses the last request to bigbasket.com from the HAR (Cookie + headers).
   - **cURL**: Click one request to bigbasket.com → “Copy as cURL”. Paste into `session.txt`. Set `"session_file": "session.txt"`.
   - **Plain headers**: One header per line, e.g. `Cookie: ...` and `User-Agent: ...` in `session.txt`.
3. **Run**: `python tracker.py -c`. The script uses that session for all requests (pincode is already set in the cookies).

Refresh the session file when cookies expire.

If `session_file` is missing or unreadable, the script falls back to the pincode API (may still get Access Denied on some networks).

## Access Denied (requests mode only)

If you use requests mode (no browser) and get “Access Denied”:

- **Use browser mode** (recommended): set `"use_browser": true` in config or run `python tracker.py -c --browser`. Chrome opens; set pincode once; no Access Denied.
- Or use a **session file** (cURL with Cookie from Chrome) in requests mode.
- Use **one pincode** and **fewer products**; run **less often**.

## Files

| File           | Purpose                                      |
|----------------|----------------------------------------------|
| `tracker.py`   | Main script                                  |
| `config.json`  | Pincodes, product_urls, use_browser (default true), optional session_file |
| `state.json`   | Last status per product/pincode              |
| `session.txt` / `session.har` | Optional: cookies/headers (cURL, plain headers, or HAR; see Session file) |
| `pincode_flow.json` | Recorded pincode steps (from `--record-pincode`); used for automatic pincode in browser mode |
| `pincode_session_record.json` | Full session record (from `record_pincode_session.py`): cookies, UI steps, network calls |
| `record_pincode_session.py` | Record your pincode flow (UI, network, cookies) and verify |
| `requirements.txt` | Python deps (requests, selenium, webdriver-manager) |

## Record and verify pincode session

To capture everything while you set the pincode (for debugging or to reuse the session):

```bash
# 1. Record: do your pincode flow, then press Enter to save
python record_pincode_session.py

# 2. Verify: load the record, set pincode via API, check the page
python record_pincode_session.py --verify
```

This saves to `pincode_session_record.json`:

- **Cookies** – applied by the tracker when present so the browser has your session
- **UI steps** – clicks and inputs (same as `pincode_flow.json`)
- **Network** – BigBasket API calls (places/autocomplete, details, serviceable)

If you run the recorder once, the main tracker will apply these cookies before setting pincode, which can make the API-based pincode setting work more reliably.
#   B B _ t r a c k e r  
 #   B B _ t r a c k e r  
 