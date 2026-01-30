# BigBasket APIs (from HAR files)

Summary of internal APIs observed in `bigbasket_stock.har` and `Bigbasket.har` for **stock check** and **pincode/location change**.

---

## 1. Stock / product data

### Next.js product page data (single product)

- **URL:** `https://www.bigbasket.com/_next/data/{buildId}/pd/{product_id}/{slug}.json`
- **Method:** GET
- **Example:** `/_next/data/TiBvbC2dBTBqbHRDcdku3/pd/10000074/fresho-cauliflower-1-pc.json?...`
- **Query:** `params={product_id}` and `params={slug}` (e.g. `params=10000074`, `params=fresho-cauliflower-1-pc`). Other query params (nc, t_pg, t_ch, etc.) are tracking/context.
- **Headers:** Normal browser headers; optional `x-nextjs-data: 1`, `x-middleware-prefetch: 1`.
- **Note:** `buildId` (e.g. `TiBvbC2dBTBqbHRDcdku3`) can change with site deployments. If the URL 404s, the buildId may need to be read from the main site (e.g. from a script tag or next config).

Using this endpoint returns JSON for that product page (including product and likely stock/availability for the current location when cookies are set).

### Other stock-related calls (from HAR)

- **basketService/get/** – basket contents
- **ui-svc/v1/door-data/?i=...** – door/location and UI config (includes `selected_address_info` with pin, lat, lng after location is set)

---

## 2. Pincode / location change

Flow observed when user changes pincode/location:

### Step 1: Autocomplete (search by pincode)

- **URL:** `https://www.bigbasket.com/places/v1/places/autocomplete/`
- **Method:** GET
- **Query:**
  - `inputText` – pincode or partial (e.g. `122001`, `122`, `12200`)
  - `token` – UUID (client-generated, e.g. `6ce2ddca-c0cf-4336-b64f-b1c234d97b32`)
- **Example:** `places/v1/places/autocomplete/?inputText=122001&token=6ce2ddca-c0cf-4336-b64f-b1c234d97b32`
- **Response:** JSON list of places (each with identifiers for step 2).

### Step 2: Place details (get lat/lng)

- **URL:** `https://www.bigbasket.com/places/v1/places/details/`
- **Method:** GET
- **Query:**
  - `placeId` – from autocomplete response (e.g. Google Place ID: `ChIJm523QqkZDTkR06eT1PrbRxM`)
  - `token` – UUID
  - `xArm`, `yArm` – optional
- **Example:** `places/v1/places/details/?placeId=ChIJm523QqkZDTkR06eT1PrbRxM&token=...&xArm=1059&yArm=202`
- **Response:** Place details including coordinates (lat/lng) used in step 3.

### Step 3: Set serviceable location

- **URL:** `https://www.bigbasket.com/ui-svc/v1/serviceable/`
- **Method:** GET
- **Query:**
  - `lat` – latitude (e.g. `28.4554726`)
  - `lng` – longitude (e.g. `77.0219019`)
  - `send_all_serviceability` – `true`
- **Example:** `ui-svc/v1/serviceable/?lat=28.4554726&lng=77.0219019&send_all_serviceability=true`
- **Response:** Serviceability info; session/cookies are updated so subsequent requests (product data, basket, etc.) use this location.

### Step 4 (optional): Migrate cart after location change

- **URL:** `https://www.bigbasket.com/order/v1/migrate-cart/`
- **Method:** GET (or POST in some flows)
- **Query:** `old_loc_info`, `new_loc_info`, `old_area`, `new_area`, `old_address_id`, etc.
- Used when user already has items in cart and changes location.

### Cookies / session

Response headers in HAR show location-related cookies, e.g.:

- `_bb_lat_long` – base64-encoded `lat|lng` (e.g. `MjguNDU1NDcyNnw3Ny4wMjE5MDE5` → `28.4554726|77.0219019`)
- `_bb_pin_code` – pincode
- `_bb_addressinfo` – address/location info

So after calling **serviceable** (and possibly **places/details**), the site sets these cookies; further API calls (e.g. product JSON, basket) then get location-specific data.

---

## 3. Common headers (from HAR)

Useful request headers for API calls:

- `User-Agent`: e.g. `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36`
- `x-channel`: `BB-WEB`
- `x-entry-context`: `bb-b2c` or `bbnow`
- `x-entry-context-id`: `100` (bigbasket) or `10` (bbnow)
- `Referer`: `https://www.bigbasket.com/`

For **authenticated** flows (e.g. after login), cookies such as `BBAUTHTOKEN`, `access_token`, `csurftoken` are also sent.

---

## 4. Using this in the tracker

- **Stock:** Prefer calling `/_next/data/{buildId}/pd/{product_id}/{slug}.json` (with optional `params=` query). If buildId is unknown, try the one from this HAR or fetch the homepage and parse buildId from the page/script. Use the same cookies (and pincode flow below) for location-specific stock.
- **Pincode:** To check stock for a pincode: (1) `places/autocomplete?inputText={pincode}&token={uuid}`, (2) from response take a place’s id → `places/details?placeId=...&token=...`, (3) from details get lat/lng → `ui-svc/v1/serviceable?lat=...&lng=...&send_all_serviceability=true`. Then call the product JSON (or other APIs) with the session/cookies set by these calls.
