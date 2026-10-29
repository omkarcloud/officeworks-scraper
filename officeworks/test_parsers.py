"""Offline tests for the Officeworks parsers, reference resolvers and value
helpers.

    python -m pytest officeworks/test_parsers.py -q

Fixtures are real responses captured 2026-10-28 (officeworks/fixtures/):
catalogue-app JSON (products, prices, categories, brands, stores,
locations), the two GraphQL facades, Algolia listings / suggestions,
Bazaarvoice reviews / questions / statistics / summary and the sitemaps.
No network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from officeworks import parsers as P, refs  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


# ---- refs -------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("LOM280BLK", "LOM280BLK"),
    ("lom280blk", "LOM280BLK"),
    (" bi2411be ", "BI2411BE"),
    ("logitech-m280-wireless-mouse-black-lom280blk", "LOM280BLK"),
    ("https://www.officeworks.com.au/shop/officeworks/p/logitech-m280-wireless-mouse-black-lom280blk", "LOM280BLK"),
    ("https://www.officeworks.com.au/shop/officeworks/p/acer-14-aspire-lite-n150-8-128gb-laptop-acd5zsa001?x=1#r", "ACD5ZSA001"),
    ("//www.officeworks.com.au/shop/officeworks/p/bic-cristal-original-ballpoint-pens-blue-12-pack-bi2411be", "BI2411BE"),
])
def test_resolve_product(value, expected):
    assert refs.resolve_product(value) == expected


@pytest.mark.parametrize("value", [
    "", "ab", "has space", "x" * 13,
    "https://example.com/shop/officeworks/p/logitech-m280-wireless-mouse-black-lom280blk",
    "https://www.officeworks.com.au/shop/officeworks/c/technology",
])
def test_resolve_product_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_product(value)


@pytest.mark.parametrize("value,expected", [
    ("office-supplies/pens/ballpoint-pens", "office-supplies/pens/ballpoint-pens"),
    ("/Technology/", "technology"),
    ("https://www.officeworks.com.au/shop/officeworks/c/office-supplies/pens?page=2", "office-supplies/pens"),
])
def test_resolve_category(value, expected):
    assert refs.resolve_category(value) == expected


@pytest.mark.parametrize("value", ["", "office supplies", "https://www.officeworks.com.au/shop/officeworks/p/x-sku1"])
def test_resolve_category_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_category(value)


@pytest.mark.parametrize("value,expected", [
    ("Logitech", "Logitech"),
    ("logitech", "logitech"),
    ("https://www.officeworks.com.au/shop/officeworks/b/Logitech", "logitech"),
    ("https://www.officeworks.com.au/campaigns/brands/logitech#/", "logitech"),
])
def test_resolve_brand(value, expected):
    assert refs.resolve_brand(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("W320", "W320"), ("w320", "W320"),
    ("https://www.officeworks.com.au/shop/officeworks/storepage/W320/VIC/Melbourne", "W320"),
])
def test_resolve_store(value, expected):
    assert refs.resolve_store(value) == expected


@pytest.mark.parametrize("value", ["", "320", "W32", "WX320", "https://www.officeworks.com.au/shop/officeworks/c/technology"])
def test_resolve_store_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_store(value)


def test_resolve_location():
    assert refs.resolve_location("3000") == ("postcode", "3000")
    assert refs.resolve_location("-37.8136, 144.9631") == ("coordinates", ("-37.8136", "144.9631"))
    assert refs.resolve_location("Fitzroy") == ("suburb", "Fitzroy")
    with pytest.raises(ValueError):
        refs.resolve_location("")
    with pytest.raises(ValueError):
        refs.resolve_location("95,200")


def test_links():
    assert refs.product_link("logitech-m280-wireless-mouse-black-lom280blk") == \
        "https://www.officeworks.com.au/shop/officeworks/p/logitech-m280-wireless-mouse-black-lom280blk"
    assert refs.category_link("technology/laptops") == "https://www.officeworks.com.au/shop/officeworks/c/technology/laptops"
    assert refs.store_link("W320", "VIC", "Russell St, Melbourne Officeworks") == \
        "https://www.officeworks.com.au/shop/officeworks/storepage/W320/VIC/Russell-St-Melbourne"
    assert refs.store_link("W331", "VIC", "Airport West") == \
        "https://www.officeworks.com.au/shop/officeworks/storepage/W331/VIC/Airport-West"
    assert refs.store_link("W320", None, "x") is None   # the bare /storepage/W320 is a 404 on the site
    assert refs.absolute("//s3-ap-southeast-2.amazonaws.com/x.jpg") == "https://s3-ap-southeast-2.amazonaws.com/x.jpg"
    assert refs.absolute("/shop/officeworks/p/x") == "https://www.officeworks.com.au/shop/officeworks/p/x"
    assert refs.absolute("") is None


# ---- value helpers ----------------------------------------------------------------------

def test_value_helpers():
    assert P._dollars(3500) == 35.0
    assert P._dollars("899700") == 8997.0
    assert P._dollars(None) is None
    assert P._rating_from_50(42) == 4.2
    assert P._bool("Yes") is True and P._bool("No") is False and P._bool("maybe") is None
    assert P._iso("2026-08-30T12:15:07.000+00:00") == "2026-08-30T12:15:07Z"
    assert P._iso("2026-10-28") == "2026-10-28"
    assert P._date_from_ms(1785110400000) == "2026-07-27"
    assert P._measure("314.8 mm") == {"value": 314.8, "unit": "mm"}
    assert P._measure("1237.9919 cm³") == {"value": 1237.9919, "unit": "cm³"}
    assert P._text("<p>Hello&nbsp;<b>world</b></p><li>one</li><li>two</li>") == "Hello world\none\ntwo"
    assert P._snake("clickAndCollect") == "click_and_collect"


# ---- product ----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def mouse():
    prices = fixture("prices_bulk.json")
    return P.parse_product(fixture("product_lom280blk.json"), price=prices["LOM280BLK"],
                           reviews=P.parse_review_summary(fixture("review_summary_lom280blk.json")))


@pytest.fixture(scope="module")
def pens():
    return P.parse_product(fixture("product_variants_bi2411be.json"))


@pytest.fixture(scope="module")
def laptop():
    return P.parse_product(fixture("product_laptop_acd5zsa001.json"))


def test_product_identity(mouse):
    assert mouse["sku"] == "LOM280BLK"
    assert mouse["name"] == "Logitech M280 Wireless Mouse Black"
    assert mouse["link"] == "https://www.officeworks.com.au/shop/officeworks/p/logitech-m280-wireless-mouse-black-lom280blk"
    assert mouse["brand"] == {"name": "Logitech", "slug": "logitech",
                              "link": "https://www.officeworks.com.au/shop/officeworks/b/logitech",
                              "logo": "https://s3-ap-southeast-2.amazonaws.com/wc-prod-pim/BrandLogo/Logitech.png"}
    assert mouse["product_type"] == "STANDARD"
    assert mouse["status"] == "De-ranging - Replen from DC"
    assert mouse["colour"] == "Black"
    assert mouse["identifiers"]["gtin"] == "097855107503"
    assert mouse["identifiers"]["manufacturer_part_number"] == "910-004295"
    assert mouse["identifiers"]["model_number"] == "M280"
    assert mouse["created_at"] == "2014-09-24"


def test_product_pricing_from_prices_row(mouse):
    assert mouse["pricing"]["price"] == 35.0
    assert mouse["pricing"]["currency"] == "AUD"
    assert mouse["pricing"]["gst_rate"] == 10.0
    assert mouse["pricing"]["gst_amount"] == 3.18
    assert mouse["pricing"]["has_business_price"] is False
    assert mouse["pricing"]["everyday_price"] == 35.0
    assert mouse["pricing"]["is_gst_exempt"] is False
    assert mouse["pricing"]["price_drop"] == {"type": "Deals", "start_date": "2026-05-28", "end_date": "2026-06-30"}


def test_product_without_price_row(pens):
    assert pens["pricing"]["price"] is None
    assert pens["pricing"]["everyday_price"] == 7.0
    assert pens["pricing"]["currency"] == "AUD"


def test_product_rating_merges_summary(mouse):
    assert mouse["rating"]["count"] == 76
    assert mouse["rating"]["average"] == 4.22
    assert mouse["rating"]["scale"] == 5
    assert mouse["rating"]["distribution"]["5"] > 0
    assert sum(mouse["rating"]["distribution"].values()) == 76
    assert mouse["rating"]["recommended_count"] + mouse["rating"]["not_recommended_count"] <= 76
    assert mouse["rating"]["questions_count"] == 51


def test_product_rating_without_summary(pens):
    assert pens["rating"] == {"average": 4.64, "count": 33, "scale": 5}


def test_product_content(mouse):
    assert mouse["description"]["long"] and "<" not in mouse["description"]["long"]
    assert mouse["description"]["meta"].startswith("Officeworks")
    assert len(mouse["features"]) >= 3 and all("<" not in f for f in mouse["features"])
    groups = {g["group"] for g in mouse["specifications"]}
    assert "General" in groups
    assert all(a["name"] and a["value"] for g in mouse["specifications"] for a in g["attributes"])
    assert mouse["warranty"] == "12 month"


def test_product_images_and_media(mouse, pens):
    assert mouse["images"]["primary"].startswith("https://s3-ap-southeast-2.amazonaws.com/")
    assert mouse["images"]["full"] and all(u.startswith("https://") for u in mouse["images"]["full"])
    assert len(mouse["images"]["thumbnails"]) == len(mouse["images"]["full"])
    assert pens["videos"] == [{"name": "BIC Cristal Ballpoint Pens", "link": "https://www.youtube.com/embed/M6HcFCa40mY?rel=0"}]
    assert pens["documents"] == []


def test_product_variants(pens, mouse):
    assert pens["variants"]["count"] == 16
    assert pens["variants"]["attributes"]["Colour"] == ["Black", "Blue", "Green", "Red"]
    current = [v for v in pens["variants"]["options"] if v["is_current"]]
    assert len(current) == 1 and current[0]["sku"] == "BI2411BE"
    other = next(v for v in pens["variants"]["options"] if v["sku"] == "BI872730BE")
    assert other["attributes"] == {"Pack Quantity": "50", "Size": "Fine", "Colour": "Blue"}
    assert other["link"].endswith("-bi872730be") and other["image"].startswith("https://")
    assert mouse["variants"]["count"] >= 1   # the mouse family lists its colour variants


def test_product_categories_and_breadcrumbs(pens):
    assert pens["breadcrumbs"][-1] == {"name": "Ballpoint Pens", "path": "office-supplies/pens/ballpoint-pens",
                                       "link": "https://www.officeworks.com.au/shop/officeworks/c/office-supplies/pens/ballpoint-pens"}
    assert pens["categories"][0]["id"] == "Web_BALLPOINT_PENS"
    assert pens["substitutes"] == ["BI42574BE"]


def test_product_accessories_and_warranty_options(mouse):
    assert mouse["accessories"], "the mouse page lists accessories"
    acc = mouse["accessories"][0]
    assert acc["sku"] and acc["name"] and acc["link"].startswith("https://www.officeworks.com.au/")
    assert mouse["warranty_options"][0]["sku"] == "ECRPLAC50"
    assert mouse["warranty_options"][0]["product_type"] == "WARRANTY"
    assert "<a" not in mouse["warranty_options"][0]["description"]


def test_product_ranging_shipping_packaging(mouse, laptop):
    assert mouse["ranging"]["is_ranged_online"] is True
    assert mouse["ranging"]["is_ranged_in_store"] is True
    assert mouse["ranging"]["is_published"] is True
    assert mouse["ranging"]["is_preorder"] is False
    assert mouse["shipping"]["delivery_min_days"] == 9 and mouse["shipping"]["delivery_max_days"] == 17
    assert mouse["shipping"]["has_express_delivery"] is True
    assert mouse["shipping"]["contains_lithium_batteries"] is False
    assert laptop["shipping"]["contains_lithium_batteries"] is True
    assert mouse["packaging"]["weight"] == {"value": 0.91, "unit": "kg"}
    assert mouse["packaging"]["package"]["weight"] == {"value": 0.132, "unit": "kg"}
    assert mouse["packaging"]["case_quantity"] == 10
    assert laptop["promo_label"] == "Deals"
    assert laptop["pricing"]["price_drop"]["type"] == "Deals"
    assert laptop["short_name"] == 'Acer Aspire Lite 14" N150 8/128GB'


def test_product_sparse_input():
    record = P.parse_product({"sku": "X1", "name": "Thing"})
    assert record["sku"] == "X1"
    assert record["link"] == "https://www.officeworks.com.au/shop/officeworks/p/X1"
    assert record["brand"] is None
    assert record["pricing"]["price"] is None
    assert record["variants"] == {"attributes": {}, "count": 0, "options": []}
    assert record["rating"] == {"average": None, "count": 0, "scale": 5}
    assert record["images"]["primary"] is None


def test_parse_prices_keeps_order_and_marks_unknown():
    rows = P.parse_prices(fixture("prices_bulk.json"), ["LOM280BLK", "INLOG4459", "NOPE123"])
    assert [r["sku"] for r in rows] == ["LOM280BLK", "INLOG4459", "NOPE123"]
    assert rows[0]["price"] == 35.0 and rows[1]["price"] == 39.0
    assert rows[2] == {"sku": "NOPE123", "price": None, "currency": "AUD", "gst_rate": None,
                       "gst_amount": None, "has_business_price": None}


def test_products_bulk_fixture_skips_unknown():
    raw = fixture("products_bulk.json")
    skus = [P.parse_product(r)["sku"] for r in raw]
    assert skus == ["LOM280BLK", "INLOG4459"]


def test_review_statistics():
    stats = P.parse_review_statistics(fixture("statistics_bulk.json"))
    assert set(stats) == {"LOM280BLK", "INLOG4459"}
    assert stats["LOM280BLK"] == {"average": 4.22, "count": 76, "scale": 5, "questions_count": 51, "answers_count": 57}


def test_review_summary_none():
    summary = P.parse_review_summary(fixture("review_summary_none.json"))
    assert summary["count"] == 0 and summary["average"] is None
    assert summary["distribution"] == {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}


# ---- Algolia listings ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def laptops():
    return P.parse_listing(fixture("search_laptop_page1.json")["results"][0], 1)


def test_listing_pagination(laptops):
    assert laptops["pagination"] == {"page": 1, "items_per_page": 24, "total_pages": 42, "total_count": 1253}
    assert len(laptops["products"]) == 24


def test_listing_hit(laptops):
    hit = laptops["products"][0]
    assert hit["sku"] == "ACD5ZSA001"
    assert hit["name"].startswith("Acer")
    assert hit["link"] == "https://www.officeworks.com.au/shop/officeworks/p/acer-14-aspire-lite-n150-8-128gb-laptop-acd5zsa001"
    assert hit["brand"] == "Acer"
    assert hit["price"] == 447.0 and hit["currency"] == "AUD"
    assert hit["image"].startswith("https://s3-ap-southeast-2.amazonaws.com/")
    assert hit["rating"]["scale"] == 5 and 0 <= (hit["rating"]["average"] or 0) <= 5
    assert hit["promo_label"] == "Deals"
    assert hit["is_clearance"] is False
    assert hit["status"] == "Active"
    assert hit["availability"]["states"][:6] == ["QLD", "NSW", "NT", "ACT", "WA", "TAS"]
    assert set(hit["availability"]["states"]) <= set(refs.AU_STATES)
    assert hit["availability"]["is_ranged_online"] is True
    assert {"name": "All Laptops", "path": "technology/laptops/all-laptops",
            "link": "https://www.officeworks.com.au/shop/officeworks/c/technology/laptops/all-laptops"} in hit["categories"]
    assert hit["attributes"]["display_size"] == "14 in"
    assert hit["attributes"]["ram_installed_size"]
    assert "product_rank_personal" not in hit["attributes"]
    assert hit["created_at"] == "2026-07-27"
    assert hit["substitutes"] == ["ACD2TSA001"]


def test_listing_facets(laptops):
    facets = laptops["facets"]
    assert facets["price_range"] == {"min": 1.0, "max": 8997.0, "average": 544.26, "currency": "AUD"}
    assert facets["brands"][0]["count"] > 0
    assert any(b["value"] == "HP" for b in facets["brands"])
    assert facets["categories"][0]["link"].startswith("https://www.officeworks.com.au/shop/officeworks/c/")
    assert facets["ratings"][0]["value"] == 5.0
    assert {s["value"] for s in facets["states"]} >= {"NSW", "VIC"}
    assert isinstance(facets["clearance_count"], int)


def test_listing_empty_and_past_end():
    empty = P.parse_listing(fixture("search_no_results.json")["results"][0], 1)
    assert empty["products"] == []
    assert empty["pagination"]["total_count"] == 0 and empty["pagination"]["total_pages"] == 0
    assert empty["facets"]["brands"] == [] and empty["facets"]["price_range"] is None
    # Algolia answers a page past the end with nbHits 0 / nbPages 0
    past = P.parse_listing(fixture("search_past_end.json")["results"][0], 1000)
    assert past["products"] == [] and past["pagination"] == {"page": 1000, "items_per_page": 24,
                                                             "total_pages": 0, "total_count": 0}


def test_listing_category_brand_clearance():
    cat = P.parse_listing(fixture("category_ballpoint_pens_algolia.json")["results"][0], 1)
    assert cat["pagination"]["total_count"] > 100
    assert all("office-supplies/pens/ballpoint-pens" in [c["path"] for c in p["categories"]] for p in cat["products"])
    brand = P.parse_listing(fixture("brand_logitech_algolia.json")["results"][0], 1)
    assert all(p["brand"].lower() == "logitech" for p in brand["products"])
    prices = [p["price"] for p in brand["products"]]
    assert prices == sorted(prices), "price-asc replica"
    clearance = P.parse_listing(fixture("clearance_algolia.json")["results"][0], 1)
    assert all(p["is_clearance"] for p in clearance["products"])


def test_suggestions():
    rows = P.parse_suggestions(fixture("suggestions_lap.json")["results"][0])
    assert rows[0]["query"] == "laptops"
    assert rows[0]["link"] == "https://www.officeworks.com.au/shop/officeworks/search?q=laptops"
    assert rows[0]["popularity"] == 15043
    assert rows[0]["result_count"] == 275
    assert rows[0]["top_categories"][0] == {"name": "All Laptops", "count": 265}
    assert P.parse_suggestions(fixture("suggestions_none.json")["results"][0]) == []


# ---- categories / brands ----------------------------------------------------------------

def test_category_tree():
    tree = P.parse_category_tree(fixture("categories_tree.json"))
    assert len(tree) >= 8
    tech = next(n for n in tree if n["path"] == "technology")
    assert tech["level"] == 1 and tech["link"] == "https://www.officeworks.com.au/shop/officeworks/c/technology"
    assert tech["children"] and tech["children"][0]["level"] == 2
    assert P._count_nodes(tree) > 500


def test_category_details():
    cat = P.parse_category(fixture("category_ballpoint_pens.json"))
    assert cat["id"] == "Web_BALLPOINT_PENS"
    assert cat["name"] == "Ballpoint Pens"
    assert cat["path"] == "office-supplies/pens/ballpoint-pens"
    assert cat["thumbnail"].startswith("https://")
    assert cat["breadcrumbs"][0] == {"name": "Office Supplies", "path": "office-supplies",
                                     "link": "https://www.officeworks.com.au/shop/officeworks/c/office-supplies"}
    assert cat["children"] == [] and cat["children_count"] == 0
    tech = P.parse_category(fixture("category_technology.json"))
    assert tech["children_count"] > 5
    assert tech["children"][0]["id"] and tech["children"][0]["path"].startswith("technology/")


def test_brands():
    rows = P.parse_brands(fixture("brands.json"))
    assert len(rows) > 500
    logitech = next(b for b in rows if b["slug"] == "logitech")
    assert logitech["name"] == "Logitech"
    assert logitech["link"] == "https://www.officeworks.com.au/shop/officeworks/b/logitech"
    assert logitech["logo"].startswith("https://")
    one = P.parse_brands(fixture("brand_logitech.json"))
    assert len(one) == 1 and one[0]["id"] == "Brand_LOGITECH"
    assert one[0]["description"].startswith("Established in 1981")
    assert one[0]["campaign_link"] == "https://www.officeworks.com.au/campaigns/brands/logitech#/"
    assert P.parse_brands(fixture("brand_unknown.json")) == []


# ---- stores -----------------------------------------------------------------------------

def test_store_details():
    store = P.parse_store(fixture("store_w320.json"))
    assert store["id"] == "W320"
    assert store["name"] == "Russell St, Melbourne Officeworks"
    assert store["link"] == "https://www.officeworks.com.au/shop/officeworks/storepage/W320/VIC/Russell-St-Melbourne"
    assert store["status"] == "Active" and store["opening_date"] == "2009-08-03"
    assert store["address"] == {"street": "QV Centre Russell Street", "located_in": None, "suburb": "Melbourne",
                                "postcode": "3000", "state": "VIC"}
    assert store["location"]["latitude"] == pytest.approx(-37.8101349)
    assert store["location"]["longitude"] == pytest.approx(144.9665296)
    assert store["contact"]["phone"] == "(03) 8665 6400"
    assert store["contact"]["email"].endswith("@officeworks.com.au")
    assert store["opening_hours"][0] == {"day": "Mon", "open": "8am", "close": "7pm"}
    assert len(store["opening_hours"]) == 7
    assert store["services"]["click_and_collect"] is True
    assert store["services"]["print_and_copy"] is True
    assert store["notice"] is None


def test_stores_by_state():
    grouped = P.parse_stores_by_state(fixture("stores_by_state.json"))
    assert list(grouped)[:3] == ["NSW", "VIC", "QLD"]
    assert sum(len(v) for v in grouped.values()) > 150
    card = grouped["VIC"][0]
    assert card["id"] == "W331" and card["address"]["state"] == "VIC"
    assert card["link"] == "https://www.officeworks.com.au/shop/officeworks/storepage/W331/VIC/Airport-West"
    assert card["phone"] == "(03) 8318 5600"


def test_stores_near_postcode():
    rows = P.parse_stores(fixture("stores_postcode_2000.json"))
    assert rows[0]["id"] == "W253"
    assert rows[0]["location"]["distance_km"] == 0.89
    distances = [r["location"]["distance_km"] for r in rows]
    assert distances == sorted(distances)
    assert rows[0]["opening_hours"] and rows[0]["services"]


def test_locations():
    rows = P.parse_locations(fixture("locations_melbourne.json"))
    assert rows[0] == {"suburb": "Melbourne", "postcode": "3000", "state": "VIC"}
    assert P.parse_locations({}) == []
    assert P.parse_location_by_coordinates(fixture("location_by_coordinates.json")) == \
        {"postcode": "3000", "suburb": "Melbourne", "state": "VIC"}
    assert P.parse_location_by_coordinates({"data": {"accountDeliveryLocationByCoordinates": None}}) is None


# ---- availability -----------------------------------------------------------------------

def test_availability():
    out = P.parse_availability(fixture("availability_lom280blk_w320.json"), "LOM280BLK", "W320", "3000", 1)
    assert out["sku"] == "LOM280BLK" and out["requested_quantity"] == 1
    assert out["store"]["id"] == "W320" and out["store"]["is_known"] is True
    assert out["store"]["name"].startswith("Russell St")
    assert out["is_ranged_online"] is True
    assert out["store"]["link"].endswith("/storepage/W320/VIC/Russell-St-Melbourne")
    assert out["click_and_collect"] == {"is_available": True, "quantity": 6, "available_date": "2026-10-29T00:00:00Z",
                                        "available_relative": "today", "is_quick_collect_available": False}
    assert out["in_store"]["quantity"] == 6 and out["in_store"]["is_available"] is True
    assert out["delivery"] is None   # the facade answers null for a leg it does not quote
    assert out["errors"] is None


def test_availability_unknown():
    assert P.parse_availability(fixture("availability_unknown_sku.json"), "NOPE123", "W320", None, 1) is None
    out = P.parse_availability(fixture("availability_unknown_store.json"), "LOM280BLK", "W999", None, 1)
    assert out["store"]["is_known"] is False
    assert out["click_and_collect"] is None and out["errors"] == ["Bad request"]


# ---- reviews / questions ----------------------------------------------------------------

def test_reviews_page():
    out = P.parse_reviews(fixture("reviews_lom280blk_page1.json"), "LOM280BLK", 1, 25)
    assert out["pagination"] == {"page": 1, "items_per_page": 25, "total_pages": 4, "total_count": 76}
    assert len(out["reviews"]) == 25
    assert out["summary"]["count"] == 76 and out["summary"]["average"] == 4.22
    assert sum(out["summary"]["distribution"].values()) == 76
    assert out["summary"]["recommended_count"] == 43
    assert out["summary"]["secondary_averages"]["Quality"] > 0
    assert out["summary"]["first_review_at"] == "2016-04-27T06:19:17Z"
    first = out["reviews"][0]
    assert first["id"] == "1228590270"
    assert first["rating"] == 1 and first["is_recommended"] is False
    assert first["secondary_ratings"] == {"Value": 1, "Quality": 1}
    assert first["purchase_context"] == {"WhereDidYouPurchase": "instore"}
    assert first["author"]["nickname"] and first["submitted_at"] == "2026-08-30T12:15:07Z"
    assert first["brand_responses"][0]["department"] == "Logitech Team"
    assert "<img" not in first["brand_responses"][0]["text"]
    assert first["product"] == {"sku": "LOM280BLK", "name": "Logitech M280 Wireless Mouse Black"}
    with_photo = next((r for r in out["reviews"] if r["photos"]), None)
    assert with_photo is None or with_photo["photos"][0]["link"].startswith("https://photos-eu.bazaarvoice.com/")
    dates = [r["submitted_at"] for r in out["reviews"]]
    assert dates == sorted(dates, reverse=True)


def test_reviews_none():
    out = P.parse_reviews(fixture("reviews_none.json"), "NOPE123", 1, 25)
    assert out["reviews"] == [] and out["summary"] is None
    assert out["pagination"]["total_pages"] == 0


def test_questions_page():
    out = P.parse_questions(fixture("questions_lom280blk_page1.json"), "LOM280BLK", 1, 20)
    assert out["pagination"]["total_count"] == 51 and out["pagination"]["total_pages"] == 3
    assert len(out["questions"]) == 20
    first = out["questions"][0]
    assert first["question"].startswith("no Light comes on")
    assert first["answers_count"] == 1 and len(first["answers"]) == 1
    answer = first["answers"][0]
    assert answer["is_brand_answer"] is True and answer["author"]["nickname"] == "Logitech Team"
    assert answer["text"].startswith("If the light")
    staff = [a for q in out["questions"] for a in q["answers"] if a["is_staff_answer"]]
    assert staff and staff[0]["author"]["badges"] == ["Staff"]
    assert P.parse_questions(fixture("questions_none.json"), "NOPE123", 1, 20)["questions"] == []


# ---- sitemaps ---------------------------------------------------------------------------

def test_sitemap_index():
    rows = P.parse_sitemap_index(fixture("sitemap_index.xml"))
    assert {r["type"] for r in rows} == {"products", "categories", "stores", "content", "campaigns"}
    assert {r["link"] for r in rows} >= {"https://www.officeworks.com.au/sitemap-products.xml"}


def test_sitemap_products():
    rows = P.parse_sitemap(fixture("sitemap_products_head.xml"), "products")
    assert len(rows) == 40
    assert rows[0]["sku"] and rows[0]["slug"].endswith(rows[0]["sku"].lower())
    assert rows[0]["link"].startswith("https://www.officeworks.com.au/shop/officeworks/p/")
    assert rows[0]["last_modified"] and rows[0]["change_frequency"]
    assert all(refs.SKU_RE.match(r["sku"]) for r in rows)


def test_sitemap_categories_stores_campaigns():
    cats = P.parse_sitemap(fixture("sitemap_categories_head.xml"), "categories")
    assert cats and all(refs.CATEGORY_RE.match(c["path"]) for c in cats)
    assert cats[0]["link"].startswith("https://www.officeworks.com.au/shop/officeworks/c/")
    stores = P.parse_sitemap(fixture("sitemap_stores.xml"), "stores")
    assert len(stores) > 150
    w320 = next(s for s in stores if s["id"] == "W320")
    assert w320["state"] == "VIC" and w320["name"] == "Russell St Melbourne"
    camps = P.parse_sitemap(fixture("sitemap_campaigns.xml"), "campaigns")
    assert camps and all(c["link"].startswith("https://www.officeworks.com.au/") for c in camps)
    content = P.parse_sitemap(fixture("sitemap_content_head.xml"), "content")
    assert len(content) == 40
    assert P.parse_sitemap("", "products") == []


# ---- api listing filters (fetch layer stubbed, no network) -------------------------------

def test_listing_filters_resolve_brand_slug_and_specials_clearance(monkeypatch):
    import config
    from urllib.parse import parse_qs
    from officeworks import api, fetch as F
    monkeypatch.setattr(config, "CACHE_ENABLED", False)
    sent = []
    monkeypatch.setattr(F, "algolia_query", lambda index, params: (sent.append(params), fixture("search_laptop_page1.json")["results"][0])[1])
    monkeypatch.setattr(F, "fetch_brand", lambda slug: [{"id": "Brand_BAND_AID", "name": "Band Aid", "seoPath": "band-aid"}] if slug == "band-aid" else [])
    common = dict(page=1, sort="bestmatch-personal", min_price=None, max_price=None, min_rating=None, state=None, in_stock_online=None)
    # a brand slug (what a brand link resolves to) must reach Algolia as the facet NAME on every listing
    api.products_search(query="plaster", brand="band-aid", category=None, clearance=None, **common)
    assert parse_qs(sent[-1])["facetFilters"] == ['[["brand:Band Aid"]]']
    # the deals collection honours clearance=true; the clearance collection neither applies nor echoes it
    out = api.specials(collection="deals", query=None, brand=None, category=None, clearance=True, **common)
    assert parse_qs(sent[-1])["facetFilters"] == ['[["categorySeoPaths:deals"], ["clearanceOnline:true"]]']
    assert out["filters"] == {"clearance": True}
    out = api.specials(collection="clearance", query=None, brand=None, category=None, clearance=False, **common)
    assert parse_qs(sent[-1])["facetFilters"] == ['[["clearanceOnline:true"]]']
    assert out["filters"] is None
