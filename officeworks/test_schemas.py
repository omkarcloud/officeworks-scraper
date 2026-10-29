"""Offline tests for the /officeworks/* request schemas.

    python -m pytest officeworks/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from officeworks import schemas  # noqa: E402

PRODUCT_LINK = "https://www.officeworks.com.au/shop/officeworks/p/logitech-m280-wireless-mouse-black-lom280blk"


def test_product_schema_accepts_sku_slug_and_link():
    assert schemas.ProductSchema().load({"product": "lom280blk"}) == {"product": "LOM280BLK"}
    assert schemas.ProductSchema().load({"product": PRODUCT_LINK}) == {"product": "LOM280BLK"}
    assert schemas.ProductSchema().load({"product": "logitech-m280-wireless-mouse-black-lom280blk"}) == {"product": "LOM280BLK"}


@pytest.mark.parametrize("value", ["", "ab", "https://example.com/p/x-lom280blk"])
def test_product_schema_rejects(value):
    with pytest.raises(ValidationError):
        schemas.ProductSchema().load({"product": value})


def test_product_schema_rejects_sibling_params():
    with pytest.raises(ValidationError):
        schemas.ProductSchema().load({"product": "LOM280BLK", "sku": "LOM280BLK"})


def test_bulk_schema():
    loaded = schemas.ProductsBulkSchema().load({"products": f" lom280blk , INLOG4459,{PRODUCT_LINK}"})
    assert loaded == {"products": ["LOM280BLK", "INLOG4459"]}
    with pytest.raises(ValidationError):
        schemas.ProductsBulkSchema().load({"products": ",".join(f"SKU{i:03d}" for i in range(21))})
    with pytest.raises(ValidationError):
        schemas.ProductsBulkSchema().load({"products": "LOM280BLK,ab"})
    with pytest.raises(ValidationError):
        schemas.ProductsBulkSchema().load({})
    loaded = schemas.ProductsPricesSchema().load({"products": ",".join(f"SKU{i:03d}" for i in range(50))})
    assert len(loaded["products"]) == 50


def test_search_schema_defaults_and_filters():
    loaded = schemas.ProductsSearchSchema().load({"query": " laptop "})
    assert loaded["query"] == "laptop"
    assert loaded["page"] == 1 and loaded["sort"] == "bestmatch-personal"
    assert loaded["brand"] is None and loaded["category"] is None
    assert loaded["clearance"] is None and loaded["in_stock_online"] is None
    loaded = schemas.ProductsSearchSchema().load({
        "query": "mouse", "page": "3", "sort": "Price_Low", "brand": "Logitech",
        "category": "https://www.officeworks.com.au/shop/officeworks/c/technology/computer-accessories",
        "min_price": "10", "max_price": "99.5", "min_rating": "4", "state": "vic", "clearance": "true",
        "in_stock_online": "1"})
    assert loaded["page"] == 3 and loaded["sort"] == "price-asc"
    assert loaded["category"] == "technology/computer-accessories"
    assert loaded["min_price"] == 10.0 and loaded["max_price"] == 99.5
    assert loaded["min_rating"] == 4 and loaded["state"] == "VIC"
    assert loaded["clearance"] is True and loaded["in_stock_online"] is True


@pytest.mark.parametrize("params", [
    {}, {"query": ""}, {"query": "x", "page": "43"}, {"query": "x", "sort": "cheapest"},
    {"query": "x", "min_rating": "6"}, {"query": "x", "state": "NY"},
    {"query": "x", "min_price": "50", "max_price": "10"}, {"query": "x", "min_price": "-1"},
    {"query": "x", "store": "W320"},
])
def test_search_schema_rejects(params):
    with pytest.raises(ValidationError):
        schemas.ProductsSearchSchema().load(params)


def test_suggestions_schema():
    assert schemas.SuggestionsSchema().load({"query": "lap"}) == {"query": "lap", "limit": 10}
    with pytest.raises(ValidationError):
        schemas.SuggestionsSchema().load({"query": "lap", "limit": "21"})


def test_availability_schema():
    loaded = schemas.AvailabilitySchema().load({"product": "lom280blk", "store": "w320"})
    assert loaded == {"product": "LOM280BLK", "store": "W320", "postcode": None, "quantity": 1}
    loaded = schemas.AvailabilitySchema().load({"product": "LOM280BLK", "store": "W320", "postcode": "3000", "quantity": "5"})
    assert loaded["postcode"] == "3000" and loaded["quantity"] == 5
    with pytest.raises(ValidationError):
        schemas.AvailabilitySchema().load({"product": "LOM280BLK"})
    with pytest.raises(ValidationError):
        schemas.AvailabilitySchema().load({"product": "LOM280BLK", "store": "W320", "postcode": "30000"})
    with pytest.raises(ValidationError):
        schemas.AvailabilitySchema().load({"product": "LOM280BLK", "store": "W320", "quantity": "0"})


def test_reviews_and_questions_schemas():
    loaded = schemas.ReviewsSchema().load({"product": "LOM280BLK"})
    assert loaded == {"product": "LOM280BLK", "page": 1, "sort": "SubmissionTime:desc"}
    assert schemas.ReviewsSchema().load({"product": "LOM280BLK", "sort": "helpful"})["sort"] == "TotalPositiveFeedbackCount:desc"
    with pytest.raises(ValidationError):
        schemas.ReviewsSchema().load({"product": "LOM280BLK", "sort": "best"})
    assert schemas.QuestionsSchema().load({"product": "LOM280BLK", "page": "2"}) == {"product": "LOM280BLK", "page": 2}


def test_category_schemas():
    assert schemas.CategorySchema().load({"category": "/Technology/Laptops/"}) == {"category": "technology/laptops"}
    loaded = schemas.CategoryProductsSchema().load({"category": "technology/laptops", "brand": "HP", "sort": "newest"})
    assert loaded["category"] == "technology/laptops" and loaded["brand"] == "HP" and loaded["sort"] == "newest"
    assert loaded["query"] is None
    # an empty optional query is None, not a len(None) crash (marshmallow validates the None)
    assert schemas.CategoryProductsSchema().load({"category": "technology", "query": ""})["query"] is None
    assert schemas.BrandProductsSchema().load({"brand": "HP", "query": "   "})["query"] is None
    assert schemas.SpecialsSchema().load({"query": ""})["query"] is None
    with pytest.raises(ValidationError):
        schemas.SpecialsSchema().load({"query": "x" * 201})
    with pytest.raises(ValidationError):
        schemas.CategoryProductsSchema().load({"category": "technology", "category2": "x"})
    with pytest.raises(ValidationError):
        schemas.CategoryProductsSchema().load({})


def test_brand_schemas():
    loaded = schemas.BrandProductsSchema().load({"brand": "https://www.officeworks.com.au/shop/officeworks/b/logitech"})
    assert loaded["brand"] == "logitech" and loaded["page"] == 1
    with pytest.raises(ValidationError):
        schemas.BrandProductsSchema().load({"brand": ""})


def test_specials_schema():
    assert schemas.SpecialsSchema().load({})["collection"] == "deals"
    assert schemas.SpecialsSchema().load({"collection": "Clearance"})["collection"] == "clearance"
    with pytest.raises(ValidationError):
        schemas.SpecialsSchema().load({"collection": "sale"})


def test_store_schemas():
    assert schemas.StoresSchema().load({}) == {"state": None}
    assert schemas.StoresSchema().load({"state": "nsw"}) == {"state": "NSW"}
    assert schemas.StoreSchema().load({"store": "https://www.officeworks.com.au/shop/officeworks/storepage/W320/VIC/Melbourne"}) == {"store": "W320"}
    loaded = schemas.StoresSearchSchema().load({"location": "3000"})
    assert loaded == {"location": "3000", "limit": 10}
    assert schemas.StoresSearchSchema().load({"location": "-37.81,144.96", "limit": "3"})["limit"] == 3
    with pytest.raises(ValidationError):
        schemas.StoresSearchSchema().load({"location": "95,200"})
    with pytest.raises(ValidationError):
        schemas.StoresSearchSchema().load({})
    assert schemas.LocationsSuggestionsSchema().load({"query": "Melb"}) == {"query": "Melb"}


def test_sitemap_schemas():
    assert schemas.SitemapProductsSchema().load({}) == {"page": 1}
    assert schemas.SitemapLinksSchema().load({"type": "Stores", "page": "2"}) == {"type": "stores", "page": 2}
    assert schemas.SitemapLinksSchema().load({}) == {"type": None, "page": 1}
    with pytest.raises(ValidationError):
        schemas.SitemapLinksSchema().load({"type": "images"})


def test_empty_schema_rejects_params():
    assert schemas.EmptySchema().load({}) == {}
    with pytest.raises(ValidationError):
        schemas.EmptySchema().load({"page": "1"})
