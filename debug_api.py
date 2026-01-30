"""One-off debug: print product list and URLs from API."""
import requests
import json

r = requests.get(
    "https://www.bigbasket.com/custompage/sysgenpd/",
    params={"type": "pc", "slug": "super-saver-sona-masoori-raw-rice-26-kg-bag"},
    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bigbasket.com/"},
    timeout=15,
)
data = r.json()
tab = data["tab_info"][0]
products = tab["product_info"]["products"]
print("Count:", len(products))
for i, p in enumerate(products):
    url = p.get("absolute_url") or ""
    pid = p.get("id") or p.get("sku")
    desc = (p.get("p_desc") or "")[:50]
    has_40300424 = "40300424" in url or str(pid) == "40300424"
    print(i, "id/sku", pid, "40300424?" if has_40300424 else "", desc)
    if has_40300424 or "super-saver-sona" in url.lower():
        print("   URL:", url)
