# Ways to Fix "Failed to fetch product page"

BigBasket is likely blocking or rate-limiting plain `requests` (bot detection). Here are options, from lightest to most reliable.

---

## 1. Better headers + delays + retries (no new deps)

**Idea:** Make requests look more like a real Chrome visit and avoid hammering the server.

- Add Chrome `Sec-CH-UA`, `Sec-CH-UA-Mobile`, `Sec-CH-UA-Platform` headers.
- Add 2–3 second delay between each product fetch (and optionally between pincodes).
- Retry on 403/429 with exponential backoff (e.g. 1 retry after 5s).

| Pros | Cons |
|------|------|
| No new dependencies | If blocking is fingerprint/JS-based, may still fail |
| Quick to implement | Slower runs (delays) |
| Works for simple rate limiting | |

**Verdict:** Try this first. If errors persist, move to 2 or 3.

---

## 2. Playwright (real browser) — **recommended**

**Idea:** Use a real headless browser (Chromium) so the site sees a normal user: JS runs, cookies and fingerprint match a real browser.

- Use `playwright` (Python) to open BigBasket, set pincode (or cookies), then visit each product URL and read HTML or `page.content()`.
- Parse stock from HTML (same `__NEXT_DATA__` / "Add to basket" logic as now).

| Pros | Cons |
|------|------|
| Most reliable for JS/bot-protected sites | Heavier: need `playwright install chromium` (~150MB) |
| Same parsing logic, just different fetch | ~2–5s per page (browser startup + load) |
| Can reuse one browser context per pincode | |

**Verdict:** Best long-term option if (1) doesn’t fix the errors.

---

## 3. Hybrid: requests first, Playwright fallback

**Idea:** Try current `requests` fetch; if we get 403 or "blocked" page, retry that product with Playwright.

- Keeps runs fast when BigBasket allows requests.
- Uses Playwright only when needed.

| Pros | Cons |
|------|------|
| Lighter when requests work | Two code paths to maintain |
| Reliable when they don’t | Playwright still required for failures |

**Verdict:** Good if we want to optimize for the “happy path” but still handle blocking.

---

## 4. Residential / rotating proxies

**Idea:** Send requests through residential IPs (e.g. Bright Data, Oxylabs) so blocking by IP is harder.

- Keep current `requests` + headers; only change proxy.

| Pros | Cons |
|------|------|
| Can help with IP-based blocking | Cost ($$) |
| No browser needed | May still get blocked (fingerprint) |
| | ToS/legal considerations |

**Verdict:** Use only if we must avoid a browser and (1)–(3) aren’t enough.

---

## 5. Scraping API (Browserless, ScrapingBee, etc.)

**Idea:** Call a service that runs a real browser in the cloud and returns HTML for a URL.

- Replace `fetch_product_page()` with a call to their API (URL + optional pincode/cookies).
- Same parsing as now.

| Pros | Cons |
|------|------|
| No local browser | Recurring cost |
| Often good at avoiding blocks | External dependency and rate limits |

**Verdict:** Reasonable if we don’t want to run Playwright ourselves.

---

## 6. Mobile app API (reverse‑engineer)

**Idea:** BigBasket’s app likely uses REST/GraphQL. Capture requests (e.g. mitmproxy), find the “product details / stock” endpoint, call it from Python with same auth/headers.

| Pros | Cons |
|------|------|
| Lightweight, structured JSON | Reverse engineering, cert pinning |
| Fast, no HTML parsing | Tokens/API may change; fragile |
| | Possible ToS issues |

**Verdict:** High effort and fragility; only if we explicitly want to avoid browsers and scraping HTML.

---

## Recommendation

1. **Implement (1)** first: better headers + 2–3s delay between requests + one retry with backoff. If most requests start succeeding, keep this and only add more if needed.
2. **If (1) still gives many errors, implement (2) Playwright** as the main fetcher: one browser context per pincode, navigate to each product URL, get `content()`, reuse current parsing. This is the most robust option without paying for proxies or external APIs.
3. Optionally add a **config flag** (e.g. `"use_browser": true`) to switch between requests-only and Playwright so you can still run the lighter path when it works.

Next step: implement (1) in the tracker, run a test; if errors remain, implement (2) behind a config flag and use that as default.
