"""Test Next.js product API and page data."""
import requests
import re
import json

# Fetch product page HTML
url = "https://www.bigbasket.com/pd/10000074/fresho-cauliflower-1-pc/"
r = requests.get(
    url,
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0",
        "Referer": "https://www.bigbasket.com/",
    },
    timeout=15,
)
print("Status", r.status_code)
# Find __NEXT_DATA__
m = re.search(r'<script id="__NEXT_DATA__"[^>]*>([^<]+)</script>', r.text)
if m:
    d = json.loads(m.group(1))
    print("__NEXT_DATA__ keys", list(d.keys()))
    if "buildId" in d:
        print("buildId", d["buildId"])
    props = d.get("props", {})
    pageProps = props.get("pageProps", {})
    if pageProps:
        print("pageProps keys", list(pageProps.keys())[:30])
        # Look for product / stock
        for k in ["product", "productInfo", "initialData", "data"]:
            if k in pageProps:
                v = pageProps[k]
                if isinstance(v, dict):
                    print(k, "keys", list(v.keys())[:15])
                else:
                    print(k, type(v))
else:
    # Try alternate pattern
    m2 = re.search(r"__NEXT_DATA__.*?>(.+?)</script>", r.text, re.DOTALL)
    if m2:
        try:
            d = json.loads(m2.group(1).strip())
            print("buildId", d.get("buildId"))
            print("pageProps keys", list(d.get("props", {}).get("pageProps", {}).keys())[:20])
        except Exception as e:
            print("Parse err", e)
    else:
        print("No __NEXT_DATA__ found. Len:", len(r.text))
