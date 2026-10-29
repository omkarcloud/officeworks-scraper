"""The /officeworks/* endpoint functions (route_glue's route_table calls
them with the schema's loaded kwargs). Caching is inside, tofler-style
(officeworks/cache_config.py): the catalogue record of a product is one
cached parse (24 h) that products/details merges with the SKU's price row
(1 h) and its Bazaarvoice summary (6 h), so a repriced product never
serves a stale price for a day; listings cache per (query, filters, page).

Listings (search / category / brand / specials) are ONE Algolia index
family: the product index `prod-product-wc-<sort replica>` with
facetFilters for brand / category / state / clearance / ranged-online and
numericFilters for price (cents) and rating (0-50). Algolia caps a query
at 1,000 hits; the honest total_pages the parser emits reflects that.
"""
import json
import math
import re
from urllib.parse import urlencode

from cache import cached_call
from officeworks import cache_config as ttl
from officeworks import parsers, refs
from officeworks import fetch as F
from officeworks.fetch import OfficeworksNotFound
from officeworks.schemas import (LISTING_PAGE_SIZE, QUESTIONS_PAGE_SIZE, REVIEWS_PAGE_SIZE, SITEMAP_PAGE_SIZE)

_EMPTY_PRICING = {"price": None, "currency": parsers.CURRENCY, "gst_rate": None, "gst_amount": None,
                  "has_business_price": None}


# ---- Algolia listings ------------------------------------------------------------

def _algolia_params(query, page, facet_filters, numeric_filters, per_page=LISTING_PAGE_SIZE):
    params = {
        "query": query or "",
        "hitsPerPage": per_page,
        "page": page - 1,
        "facets": json.dumps(["brand", "categorySeoPaths", "colour", "rating", "price", "availState", "clearanceOnline"]),
        "maxValuesPerFacet": 50,
        "clickAnalytics": "false",
    }
    if facet_filters:
        params["facetFilters"] = json.dumps(facet_filters)
    if numeric_filters:
        params["numericFilters"] = json.dumps(numeric_filters)
    return urlencode(params)


def _find_category(nodes, path):
    for node in nodes:
        if node.get("path") == path:
            return node
        found = _find_category(node.get("children") or [], path)
        if found:
            return found
    return None


def _descendant_paths(node):
    out = [node["path"]] if node.get("path") else []
    for child in node.get("children") or []:
        out.extend(_descendant_paths(child))
    return out


def _category_paths(category):
    """The paths a category filter must OR together. The index tags every
    product with the paths it is listed under, and a parent like
    technology/laptops is a landing page: its products live under
    technology/laptops/all-laptops etc. (the site's own listing filter is
    the exact path). So a filter on any path is the path plus every
    descendant from the cached tree (technology = 530 paths, 6,840 hits;
    one Algolia round trip either way)."""
    node = _find_category(categories()["categories"], category)
    return _descendant_paths(node) if node else [category]


def _listing_filters(brand=None, category=None, min_price=None, max_price=None, min_rating=None,
                     state=None, clearance=None, in_stock_online=None, extra_facets=()):
    facet_filters = [[f] for f in extra_facets]
    if brand:
        # a slug / brand link ("band-aid") must become the facet name ("Band Aid")
        facet_filters.append([f"brand:{_resolve_brand(brand)[0]}"])
    if category:
        facet_filters.append([f"categorySeoPaths:{p}" for p in _category_paths(category)])
    if state:
        facet_filters.append([f"availState:{state}"])
    if clearance is not None:
        facet_filters.append([f"clearanceOnline:{'true' if clearance else 'false'}"])
    if in_stock_online is not None:
        facet_filters.append([f"rangedOnline:{'true' if in_stock_online else 'false'}"])
    numeric = []
    if min_price is not None:
        numeric.append(f"price>={int(round(min_price * 100))}")
    if max_price is not None:
        numeric.append(f"price<={int(round(max_price * 100))}")
    if min_rating is not None:
        numeric.append(f"rating>={int(min_rating) * 10}")
    return facet_filters, numeric


def _run_listing(query, page, sort, facet_filters, numeric_filters):
    index = f"{F.ALGOLIA_PRODUCT_INDEX}-{sort}"
    result = F.algolia_query(index, _algolia_params(query, page, facet_filters, numeric_filters))
    return parsers.parse_listing(result, page)


def _applied(data, keys):
    return {k: data.get(k) for k in keys if data.get(k) not in (None, "", [])}


_FILTER_KEYS = ("brand", "category", "min_price", "max_price", "min_rating", "state", "clearance", "in_stock_online")


def _products_search(query, page, sort, **filters):
    facet_filters, numeric = _listing_filters(**{k: filters.get(k) for k in _FILTER_KEYS})
    listing = _run_listing(query, page, sort, facet_filters, numeric)
    return {"query": query, "sort": sort, "filters": _applied(filters, _FILTER_KEYS) or None, **listing}


def products_search(**data):
    """Full-text product search with the site's own filters and sorts."""
    return cached_call("officeworks.search", data, _products_search, ttl.LISTING_CACHE)


def _suggestions(query, limit):
    result = F.algolia_query(F.ALGOLIA_SUGGEST_INDEX, urlencode({"query": query, "hitsPerPage": limit}))
    suggestions = parsers.parse_suggestions(result)[:limit]
    return {"query": query, "count": len(suggestions), "suggestions": suggestions}


def products_suggestions(**data):
    """Query completions from the site's search box (with the categories each
    one lands in)."""
    return cached_call("officeworks.suggestions", data, _suggestions, ttl.SUGGESTIONS_CACHE)


# ---- product record + price + reviews ----------------------------------------------

def _product_record(product):
    return parsers.parse_product(F.fetch_product(product))


def _record(sku):
    return cached_call("officeworks.product", {"product": sku}, _product_record, ttl.PRODUCT_CACHE)


def _price_rows(products):
    return parsers.parse_prices(F.fetch_prices(products), products)


def _prices(skus):
    """[{sku, price, ...}] in the requested order, one cache row per SKU
    list (details asks for one SKU, bulk for its list)."""
    return cached_call("officeworks.prices", {"products": list(skus)}, _price_rows, ttl.PRICE_CACHE)


def _review_summary(product):
    return parsers.parse_review_summary(F.fetch_review_summary(product))


def _summary(sku):
    return cached_call("officeworks.review_summary", {"product": sku}, _review_summary, ttl.REVIEW_STATS_CACHE)


def _statistics(products):
    return parsers.parse_review_statistics(F.fetch_review_statistics(products))


def _stats(skus):
    return cached_call("officeworks.review_stats", {"products": list(skus)}, _statistics, ttl.REVIEW_STATS_CACHE)


def _merge_price(record, price_row):
    row = {k: v for k, v in (price_row or {}).items() if k != "sku"}
    record["pricing"] = {**_EMPTY_PRICING, **record.get("pricing", {}), **row}
    return record


def product_details(product):
    """The full catalogue record + the live price + the review summary."""
    record = _record(product)
    _merge_price(record, _prices([product])[0])
    summary = _summary(product)
    if summary and (summary.get("count") or record["rating"].get("count")):
        record["rating"] = {**record["rating"], **summary}
    return record


def _products_bulk(products):
    found = {}
    for raw in F.fetch_products(products):
        parsed = parsers.parse_product(raw)
        if parsed.get("sku"):
            found[parsed["sku"]] = parsed
    prices = {row["sku"]: row for row in _price_rows(products)}
    stats = _statistics(products) if found else {}
    out = []
    for sku in products:
        record = found.get(sku)
        if record is None:
            continue
        _merge_price(record, prices.get(sku))
        if stats.get(sku):
            record["rating"] = {**record["rating"], **stats[sku]}
        out.append(record)
    missing = [sku for sku in products if sku not in found]
    return {"count": len(out), "products": out, "missing": missing}


def products_bulk(products):
    """Up to 20 full records in one call; unknown SKUs are listed under
    `missing` rather than failing the batch."""
    return cached_call("officeworks.products_bulk", {"products": products}, _products_bulk, ttl.PRICE_CACHE)


def products_prices(products):
    """Current price + GST for up to 50 SKUs (null price = not priced online)."""
    rows = _prices(products)
    return {"count": sum(1 for r in rows if r.get("price") is not None), "prices": rows}


def _availability(product, store, postcode, quantity):
    raw = F.fetch_availability(product, store, postcode, quantity)
    parsed = parsers.parse_availability(raw, product, store, postcode, quantity)
    if parsed is None:
        raise OfficeworksNotFound(f"product {product} not found")
    if not parsed["store"]["is_known"]:
        raise OfficeworksNotFound(f"store {store} not found")
    return parsed


def products_availability(**data):
    """Click & Collect / in-store / delivery stock for one SKU at one store."""
    return cached_call("officeworks.availability", data, _availability, ttl.AVAILABILITY_CACHE)


def _reviews(product, page, sort):
    raw = F.fetch_reviews(product, REVIEWS_PAGE_SIZE, (page - 1) * REVIEWS_PAGE_SIZE, sort)
    return {**parsers.parse_reviews(raw, product, page, REVIEWS_PAGE_SIZE), "sort": sort}


def products_reviews(**data):
    """Customer reviews (Bazaarvoice) with the product's rating summary."""
    return cached_call("officeworks.reviews", data, _reviews, ttl.REVIEWS_CACHE)


def _questions(product, page):
    raw = F.fetch_questions(product, QUESTIONS_PAGE_SIZE, (page - 1) * QUESTIONS_PAGE_SIZE)
    return parsers.parse_questions(raw, product, page, QUESTIONS_PAGE_SIZE)


def products_questions(**data):
    """Customer questions with their answers (staff / brand flagged)."""
    return cached_call("officeworks.questions", data, _questions, ttl.QUESTIONS_CACHE)


# ---- categories --------------------------------------------------------------------

def _category_tree():
    tree = parsers.parse_category_tree(F.fetch_categories())
    return {"count": parsers._count_nodes(tree), "categories": tree}


def categories():
    """The whole department > category > subcategory tree."""
    return cached_call("officeworks.categories", {}, _category_tree, ttl.CATEGORIES_CACHE)


def _category(category):
    return parsers.parse_category(F.fetch_category(category))


def category_details(category):
    """One category's metadata, breadcrumbs and children."""
    return cached_call("officeworks.category", {"category": category}, _category, ttl.CATEGORIES_CACHE)


def _category_products(category, page, sort, query=None, **filters):
    info = category_details(category)   # cached; 404 for an unknown path
    facet_filters, numeric = _listing_filters(category=category, **{k: filters.get(k) for k in _FILTER_KEYS if k != "category"})
    listing = _run_listing(query, page, sort, facet_filters, numeric)
    head = {k: info.get(k) for k in ("id", "name", "path", "link", "breadcrumbs")}
    return {"category": head, "query": query, "sort": sort,
            "filters": _applied(filters, _FILTER_KEYS) or None, **listing}


def category_products(**data):
    """A category's product listing with the same filters and sorts as search."""
    return cached_call("officeworks.category_products", data, _category_products, ttl.LISTING_CACHE)


# ---- brands ------------------------------------------------------------------------

def _brands():
    brands = parsers.parse_brands(F.fetch_brands())
    return {"count": len(brands), "brands": brands}


def brands():
    """Every brand the site lists (name, slug, logo, description)."""
    return cached_call("officeworks.brands", {}, _brands, ttl.BRANDS_CACHE)


def _brand_lookup(slug):
    rows = parsers.parse_brands(F.fetch_brand(slug))
    return rows[0] if rows else None


def _brand_by_slug(slug):
    return cached_call("officeworks.brand", {"slug": slug}, _brand_lookup, ttl.BRANDS_CACHE)


def _slugify(value):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def _resolve_brand(value):
    """A brand name / slug -> (facet name for Algolia, brand metadata or None).
    The slug form is looked up through /brands/?seoPath= (cached); a name
    is used as is (Algolia's brand facet is case-insensitive)."""
    slug = value if refs.SLUG_RE.match(value) else _slugify(value)
    info = _brand_by_slug(slug) if slug else None
    if info and info.get("name"):
        return info["name"], info
    return value, None


def _brand_products(brand, page, sort, query=None, **filters):
    name, info = _resolve_brand(brand)
    facet_filters, numeric = _listing_filters(brand=name, **{k: filters.get(k) for k in _FILTER_KEYS if k != "brand"})
    listing = _run_listing(query, page, sort, facet_filters, numeric)
    if info is None and not listing["pagination"]["total_count"] and page == 1:
        raise OfficeworksNotFound(f"brand {brand!r} not found")
    head = {k: info.get(k) for k in ("id", "name", "slug", "link", "logo", "description", "campaign_link")} \
        if info else {"name": name, "slug": None, "link": None, "logo": None, "description": None, "campaign_link": None}
    return {"brand": head, "query": query, "sort": sort,
            "filters": _applied(filters, _FILTER_KEYS) or None, **listing}


def brand_products(**data):
    """A brand's product listing with the same filters and sorts as search."""
    return cached_call("officeworks.brand_products", data, _brand_products, ttl.LISTING_CACHE)


# ---- specials -----------------------------------------------------------------------

def _specials(collection, page, sort, query=None, **filters):
    if collection == "clearance":
        extra = ("clearanceOnline:true",)
        filters.pop("clearance", None)   # implied by the collection, never echoed as a filter
    else:
        extra = (f"categorySeoPaths:{collection}",)
    kwargs = {k: filters.get(k) for k in _FILTER_KEYS}
    facet_filters, numeric = _listing_filters(extra_facets=extra, **kwargs)
    listing = _run_listing(query, page, sort, facet_filters, numeric)
    return {"collection": collection, "query": query, "sort": sort,
            "filters": _applied(filters, _FILTER_KEYS) or None, **listing}


def specials(**data):
    """The Deals landing (collection=deals) or every clearance-priced product
    (collection=clearance), with the listing filters."""
    return cached_call("officeworks.specials", data, _specials, ttl.LISTING_CACHE)


# ---- stores ------------------------------------------------------------------------

def _stores_by_state():
    return parsers.parse_stores_by_state(F.fetch_stores())


def _all_stores():
    return cached_call("officeworks.stores", {}, _stores_by_state, ttl.STORES_CACHE)


def stores(state=None):
    """Every store grouped by state, or one state's list."""
    grouped = _all_stores()
    if state:
        rows = grouped.get(state, [])
        return {"state": state, "count": len(rows), "stores": rows}
    return {"count": sum(len(v) for v in grouped.values()),
            "states": {k: len(v) for k, v in grouped.items()}, "stores": grouped}


def _store(store):
    return parsers.parse_store(F.fetch_store(store))


def store_details(store):
    """One store: address, coordinates, hours, exception hours, services."""
    return cached_call("officeworks.store", {"store": store}, _store, ttl.STORES_CACHE)


def _locate(location):
    """Free-text location -> {postcode, suburb, state} (None when nothing
    matches): a postcode as typed, lat,lng through the site's geocoder,
    a suburb through its own location suggestions."""
    kind, value = refs.resolve_location(location)
    if kind == "postcode":
        return {"postcode": value, "suburb": None, "state": None}
    if kind == "coordinates":
        return parsers.parse_location_by_coordinates(F.fetch_location_by_coordinates(*value))
    rows = _locations_list(value)
    return rows[0] if rows else None


def _stores_search(location, limit):
    where = _locate(location)
    rows = []
    if where and where.get("postcode"):
        try:
            rows = parsers.parse_stores(F.fetch_stores_by_postcode(where["postcode"], limit))
        except OfficeworksNotFound:
            rows = []
    return {"location": {"input": location, **(where or {"postcode": None, "suburb": None, "state": None})},
            "count": len(rows), "stores": rows[:limit]}


def stores_search(**data):
    """Nearest stores to a postcode, a suburb name or lat,lng coordinates."""
    return cached_call("officeworks.stores_search", data, _stores_search, ttl.STORES_SEARCH_CACHE)


def _locations(query):
    try:
        return parsers.parse_locations(F.fetch_locations(query))
    except OfficeworksNotFound:
        return []


def _locations_list(query):
    return cached_call("officeworks.locations", {"query": query}, _locations, ttl.LOCATIONS_CACHE)


def locations_suggestions(query):
    """Suburb / postcode completions from the site's own location box."""
    rows = _locations_list(query)
    return {"query": query, "count": len(rows), "locations": rows}


# ---- sitemaps -----------------------------------------------------------------------

def _sitemap_entries(type):
    return parsers.parse_sitemap(F.fetch_sitemap(type), type)


def _sitemap(kind):
    return cached_call("officeworks.sitemap", {"type": kind}, _sitemap_entries, ttl.SITEMAP_CACHE)


def _sitemap_index():
    return parsers.parse_sitemap_index(F.fetch_sitemap(None))


def _index():
    return cached_call("officeworks.sitemap_index", {}, _sitemap_index, ttl.SITEMAP_CACHE)


def _page(rows, page, per_page):
    total = len(rows)
    start = (page - 1) * per_page
    return rows[start:start + per_page], {
        "page": page, "items_per_page": per_page,
        "total_pages": math.ceil(total / per_page) if per_page else 0, "total_count": total,
    }


def sitemap_products(page):
    """Every product URL on the site (40k, 1,000 per page) with its SKU."""
    rows, pagination = _page(_sitemap("products"), page, SITEMAP_PAGE_SIZE)
    return {"type": "products", "products": rows, "pagination": pagination}


def sitemap_links(page, type=None):
    """Every URL the site publishes in its sitemaps, all types or one."""
    kinds = [type] if type else list(refs.SITEMAP_TYPES)
    rows = []
    for kind in kinds:
        rows.extend({"type": kind, **entry} for entry in _sitemap(kind))
    rows, pagination = _page(rows, page, SITEMAP_PAGE_SIZE)
    return {"type": type, "sitemaps": _index(), "links": rows, "pagination": pagination}
