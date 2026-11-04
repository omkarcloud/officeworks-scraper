# 📎 Officeworks Scraper

Officeworks Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Officeworks Australia data for free.

## ✨ What Can I Get?

- 💻 **Full details on 40K+ products** — live price + GST, specs, features, images, variants, barcodes & delivery times
- 🔍 **Search & browse 1,250+ categories and 850+ brands** — keyword search, price & rating filters, deals & clearance
- ⭐ **Every customer review & Q&A** — full text, star breakdown, pros & cons, photos, staff and brand answers
- 📍 **All 170+ stores with live stock** — Click & Collect, in-store and delivery quantities, opening hours & services

## 💻 Example: A Full Officeworks Product

```json
{
  "sku": "MBAM5TS5MT",
  "name": "MacBook Air 13\" M5 10-Core CPU 8-Core GPU 16/512GB Midnight",
  "link": "https://www.officeworks.com.au/shop/officeworks/p/macbook-air-13-m5-10-core-cpu-8-core-gpu-16-512gb-midnight-mbam5ts5mt",
  "brand": { "name": "Apple", "slug": "apple", "link": "https://www.officeworks.com.au/shop/officeworks/b/apple" },
  "pricing": { "price": 1747.0, "currency": "AUD", "gst_rate": 10.0, "gst_amount": 158.82, "everyday_price": 1747.0, "has_business_price": false },
  "description": { "long": "MacBook Air with the M5 chip brings blazing-fast speed and powerful AI capabilities into an incredibly portable design." },
  "specifications": [
    {
      "group": "Processor and Memory",
      "attributes": [
        { "name": "Primary Processor Type", "value": "Apple M5 Chip" },
        { "name": "RAM Installed Size", "value": "16 GB" },
        { "name": "Processor Clock Speed", "value": "4.6 GHz" }
      ]
    },
    { "group": "Display", "attributes": [{ "name": "Display Resolution", "value": "2560 x 1664" }] }
  ],
  "identifiers": { "gtin": "195950690378", "manufacturer_part_number": "MDHE4X-A", "model_number": "MDHE4X/A" },
  "images": { "primary": "https://s3-ap-southeast-2.amazonaws.com/wc-prod-pim/JPEG_1000x1000/MBAM5TS5MT_macbook_air_13_m5_10_core_cpu_8_core_gpu_16_512gb_midnight.jpg" },
  "variants": {
    "attributes": { "Variation": ["16 GB RAM", "24 GB RAM"], "Colour": ["Midnight", "Silver", "Sky Blue", "Starlight"], "Capacity": ["512 GB", "1 TB"] },
    "count": 12
  },
  "breadcrumbs": [
    { "name": "Technology", "path": "technology", "link": "https://www.officeworks.com.au/shop/officeworks/c/technology" },
    { "name": "Laptops", "path": "technology/laptops", "link": "https://www.officeworks.com.au/shop/officeworks/c/technology/laptops" }
  ],
  "rating": { "average": 5.0, "count": 9, "distribution": { "5": 9, "4": 0, "3": 0, "2": 0, "1": 0 }, "questions_count": 10, "answers_count": 10 },
  "shipping": { "delivery_min_days": 8, "delivery_max_days": 10, "has_express_delivery": true, "returns_window": "30 days" },
  "warranty": "12 month"
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Officeworks Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/officeworks-scraper
cd officeworks-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/products/details?product=MBAM5TS5MT"
```

```json
{
  "sku": "MBAM5TS5MT",
  "name": "MacBook Air 13\" M5 10-Core CPU 8-Core GPU 16/512GB Midnight",
  "link": "https://www.officeworks.com.au/shop/officeworks/p/macbook-air-13-m5-10-core-cpu-8-core-gpu-16-512gb-midnight-mbam5ts5mt",
  "brand": { "name": "Apple", "slug": "apple", "link": "https://www.officeworks.com.au/shop/officeworks/b/apple" },
  "pricing": { "price": 1747.0, "currency": "AUD", "gst_rate": 10.0, "gst_amount": 158.82, "everyday_price": 1747.0 },
  "identifiers": { "gtin": "195950690378", "manufacturer_part_number": "MDHE4X-A", "model_number": "MDHE4X/A" },
  "variants": { "count": 12, "attributes": { "Colour": ["Midnight", "Silver", "Sky Blue", "Starlight"], "Capacity": ["512 GB", "1 TB"] } },
  "rating": { "average": 5.0, "count": 9, "scale": 5, "recommended_count": 5, "questions_count": 10, "answers_count": 10 },
  "ranging": { "is_ranged_online": true, "is_ranged_in_store": true, "is_published": true, "sales_channel": "Both" },
  "shipping": { "delivery_min_days": 8, "delivery_max_days": 10, "has_express_delivery": true, "delivery_method": "Direct To Store", "returns_window": "30 days" },
  "warranty": "12 month",
  "created_at": "2026-03-04"
}
```

All 20 endpoints are now live at `http://localhost:8000`.

Product, price, stock, category, brand, store or sitemap endpoints answering 500 "blocked"? Officeworks' AWS WAF shows some IPs a "Human Verification" page. Set `OFFICEWORKS_PROXY` to an Australian proxy (`http://user:pass@host:port`) and they work. Search, suggestions, deals, reviews and questions never need one.

## 📚 Endpoints

20 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Product Details | `/products/details` | Everything about one product in a single call |
| Search Products | `/products/search` | 24 products per page; filter by brand, category, price, rating, state |
| Search Suggestions | `/products/suggestions` | Search-box completions with popularity and result counts |
| Product Reviews | `/products/reviews` | Full reviews, 25 per page, with the star breakdown |
| Product Questions | `/products/questions` | Customer Q&A, 20 per page, staff and brand answers flagged |
| Store Stock | `/products/availability` | Click & Collect, in-store and delivery stock at one store |
| Bulk Product Details | `/products/bulk` | Up to 20 full product records in one call |
| Bulk Prices | `/products/prices` | Live price + GST for up to 50 products |
| All Categories | `/categories` | The full 1,250+ category tree in one call |
| Category Details | `/categories/details` | Name, description, breadcrumbs and child categories |
| Category Products | `/categories/products` | A category's products, subcategories included, every search filter |
| All Brands | `/brands` | All 850+ brands with logos and descriptions |
| Brand Products | `/brands/products` | A brand's full Officeworks range, every search filter |
| Deals & Clearance | `/specials` | Every deal or clearance-priced product, fully filterable |
| All Stores | `/stores` | All 170+ stores grouped by state |
| Find Stores | `/stores/search` | Nearest stores to a postcode, suburb or GPS point |
| Store Details | `/stores/details` | Address, phone, opening hours, holiday hours and services |
| Location Suggestions | `/locations/suggestions` | Suburb and postcode completions with state |
| All Product Links | `/sitemap/products` | Every product URL with its SKU, 1,000 per page |
| All Sitemap Links | `/sitemap/links` | Every URL in the site's sitemaps, 1,000 per page |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-officeworks-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-officeworks-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-officeworks-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/products/search",
    params={"query": "macbook air", "sort": "price_low"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Officeworks Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://www.omkar.cloud/l/officeworks-scraper-github-whatsapp)

[![Ask Us by Email about Officeworks Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Officeworks%20Scraper%20API&body=I%20need%20help%20using%20the%20Officeworks%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations
- [**Kmart Scraper**](https://github.com/omkarcloud/kmart-scraper) — Kmart Australia products, prices, stock by state, reviews & stores

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/officeworks-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/officeworks-scraper)
