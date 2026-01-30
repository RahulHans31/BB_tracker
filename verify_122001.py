"""
Verify stock for Fresho Cauliflower at pincode 122001.
Uses HAR flow: places autocomplete -> details -> serviceable, then fetch product data.
"""
import json
import uuid
import requests

BASE = "https://www.bigbasket.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE + "/",
    "Accept": "application/json, */*",
    "x-channel": "BB-WEB",
    "x-entry-context-id": "100",
}

def main():
    s = requests.Session()
    s.headers.update(HEADERS)

    pincode = "122001"
    token = str(uuid.uuid4()).replace("-", "")[:32]

    # 1. Places autocomplete
    r1 = s.get(
        BASE + "/places/v1/places/autocomplete/",
        params={"inputText": pincode, "token": token},
        timeout=15,
    )
    print("1. Autocomplete status:", r1.status_code)
    if not r1.ok:
        print("   Body:", r1.text[:300])
        return
    places = r1.json()
    if not places:
        print("   No places found for pincode", pincode)
        return
    # Response can be list or dict with predictions/results
    if isinstance(places, dict):
        plist = places.get("predictions") or places.get("results") or places.get("places") or []
    else:
        plist = places
    if not plist:
        print("   Empty places list. Response keys:", list(places.keys()) if isinstance(places, dict) else "list len " + str(len(places)))
        return
    first = plist[0] if isinstance(plist[0], dict) else plist
    place_id = first.get("place_id") or first.get("id") or first.get("placeId") or first.get("place_id")
    if not place_id:
        print("   First place keys:", list(first.keys()) if isinstance(first, dict) else first)
        return
    print("   First place id:", place_id)

    # 2. Place details (get lat/lng)
    token2 = str(uuid.uuid4()).replace("-", "")[:32]
    r2 = s.get(
        BASE + "/places/v1/places/details/",
        params={"placeId": place_id, "token": token2},
        timeout=15,
    )
    print("2. Details status:", r2.status_code)
    if not r2.ok:
        print("   Body:", r2.text[:300])
        return
    details = r2.json()
    lat = details.get("lat") or details.get("latitude")
    lng = details.get("lng") or details.get("longitude")
    if lat is None or lng is None:
        # try nested
        geo = details.get("geometry", {}).get("location", details)
        lat = lat or geo.get("lat")
        lng = lng or geo.get("lng")
    print("   Lat/Lng:", lat, lng)

    # 3. Serviceable (set location)
    r3 = s.get(
        BASE + "/ui-svc/v1/serviceable/",
        params={"lat": lat, "lng": lng, "send_all_serviceability": "true"},
        timeout=15,
    )
    print("3. Serviceable status:", r3.status_code)
    print("   Cookies after serviceable:", list(s.cookies.keys()))

    # 4. Try Next.js product API (buildId from HAR)
    build_id = "TiBvbC2dBTBqbHRDcdku3"
    pd_url = f"{BASE}/_next/data/{build_id}/pd/10000074/fresho-cauliflower-1-pc.json"
    r4 = s.get(pd_url, params={"params": ["10000074", "fresho-cauliflower-1-pc"]}, timeout=15)
    print("4. Next.js product status:", r4.status_code)
    if r4.ok and r4.text:
        try:
            data = r4.json()
            print("   Keys:", list(data.keys()))
            if "pageProps" in data:
                pp = data["pageProps"]
                print("   pageProps keys:", list(pp.keys())[:25])
        except Exception as e:
            print("   Parse error:", e)
            print("   Body sample:", r4.text[:400])

    # 5a. Try slug fresho-cauliflower-1-pc with session (maybe location-specific)
    r5a = s.get(BASE + "/custompage/sysgenpd/", params={"type": "pc", "slug": "fresho-cauliflower-1-pc"}, timeout=15)
    if r5a.ok:
        d = r5a.json()
        tab = d.get("tab_info", [{}])[0]
        pi = tab.get("product_info", {})
        prods = pi.get("products", []) if isinstance(pi, dict) else []
        found = next((p for p in prods if str(p.get("sku")) == "10000074"), None)
        if found:
            av = found.get("store_availability", [])
            in_stock = any(x.get("pstat") == "A" for x in av)
            print("5a. Found 10000074 via slug fresho-cauliflower-1-pc. IN_STOCK:", in_stock)
        else:
            print("5a. Slug fresho-cauliflower-1-pc: count", len(prods), ", first sku", prods[0].get("sku") if prods else None)

    # 5b. Sysgenpd fresh-vegetables - paginate to find product 10000074
    slug = "fresh-vegetables"
    for page in range(1, 6):
        r5 = s.get(
            BASE + "/custompage/sysgenpd/",
            params={"type": "pc", "slug": slug, "page": page},
            timeout=20,
        )
        if not r5.ok:
            print("5. Sysgenpd page", page, "status:", r5.status_code)
            break
        d = r5.json()
        tab = d.get("tab_info", [{}])[0]
        pi = tab.get("product_info", {})
        prods = pi.get("products", []) if isinstance(pi, dict) else []
        tot_pages = pi.get("tot_pages", 1) if isinstance(pi, dict) else 1
        found = next((p for p in prods if str(p.get("sku")) == "10000074"), None)
        if found:
            av = found.get("store_availability", [])
            pstats = [x.get("pstat") for x in av]
            in_stock = any(p == "A" for p in pstats)
            print("5. Found 10000074 on page", page)
            print("   store_availability pstat:", pstats[:8])
            print("   IN_STOCK:", in_stock)
            print("   Product:", (found.get("p_desc") or "")[:50])
            break
        if page >= tot_pages:
            print("5. Product 10000074 not in", tot_pages, "pages of", slug)
            break
    else:
        print("5. Product 10000074 not in first 5 pages")

if __name__ == "__main__":
    main()
