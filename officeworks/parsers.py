"""Raw Officeworks JSON / XML -> clean dicts. Pure functions, no I/O.

Fixtures (officeworks/fixtures/, captured 2026-10-28 from the live site):
  * catalogue-app JSON: product_lom280blk.json (standard product, 76
    reviews, accessories, warranty option, de-ranging status),
    product_variants_bi2411be.json (16-variant family, video attachment),
    product_laptop_acd5zsa001.json (on a Deals price drop), products_bulk
    .json, prices_bulk.json, categories_tree.json, category_*.json,
    brands.json, brand_logitech.json, brand_unknown.json ([]),
    stores_by_state.json, store_w320.json, stores_postcode_2000.json,
    locations_melbourne.json
  * GraphQL: availability_lom280blk_w320.json, availability_unknown_sku
    .json (product null), availability_unknown_store.json (errors +
    empty store), nearest_stores_rich_probe.json, location_by_coordinates
    .json
  * Algolia: search_laptop_page1.json (24 hits + facets), search_no_results
    .json, search_past_end.json, category_ballpoint_pens_algolia.json,
    brand_logitech_algolia.json, clearance_algolia.json, suggestions_lap
    .json, suggestions_none.json
  * Bazaarvoice: reviews_lom280blk_page1.json, reviews_none.json,
    questions_lom280blk_page1.json, questions_none.json,
    statistics_bulk.json, review_summary_lom280blk.json,
    review_summary_none.json
  * sitemaps: sitemap_index.xml, sitemap_stores.xml, sitemap_campaigns.xml,
    sitemap_{products,categories,content}_head.xml (first 40 URLs each)

Conventions: prices in AUD dollars (the site serves cents), Algolia's 0-50
rating scale -> 0-5, ISO-8601 UTC timestamps, null for anything absent.
"""
import html
import math
import re
from datetime import datetime, timezone

from officeworks import refs

CURRENCY = "AUD"

# The site's promo "dinkus" codes -> the label its product cards show.
PROMO_LABELS = {
    "dinkusDeals": "Deals",
    "dinkusClearance": "Clearance",
    "dinkusLowPrices": "Low Price",
    "dinkusNew": "New",
    "dinkusBYOD": "BYOD",
    "dinkusPlanetPositive": "Planet Positive",
    "dinkusPeopleAndPlanetPositive": "People and Planet Positive",
    "dinkusOnePass": "OnePass",
    "dinkusBestSeller": "Best Seller",
}

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# ---- value helpers ----------------------------------------------------------------

def _str(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value)


def _int(value):
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float(value):
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def _dollars(cents):
    """Catalogue / Algolia prices are integer cents (3500 = $35.00)."""
    value = _int(cents)
    return round(value / 100, 2) if value is not None else None


def _money_str(value):
    """edlpPrice is a dollar string ("7.00")."""
    return _float(value)


def _bool(value):
    """True/False, "Yes"/"No", "true"/"false" -> bool; anything else None."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    low = str(value).strip().lower()
    if low in ("yes", "true", "y", "1"):
        return True
    if low in ("no", "false", "n", "0"):
        return False
    return None


def _rating_from_50(value):
    """Algolia stores the average rating as 0-50 (37 = 3.7 stars)."""
    value = _int(value)
    return round(value / 10, 1) if value is not None else None


def _iso(value):
    """Bazaarvoice "2026-08-30T12:15:07.000+00:00" -> "2026-08-30T12:15:07Z";
    a date-only string passes through; anything else None."""
    value = _str(value)
    if not value:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.replace(tzinfo=None, microsecond=0).isoformat() + "Z"


def _date_from_ms(value):
    value = _int(value)
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _text(value):
    """HTML -> plain text (tags stripped, entities decoded, whitespace
    collapsed); None when nothing is left."""
    value = _str(value)
    if not value:
        return None
    value = re.sub(r"</?(?:li|p|div|br|h[1-6]|tr)\b[^>]*>", "\n", value, flags=re.I)
    text = html.unescape(_TAG_RE.sub(" ", value))
    lines = [_WS_RE.sub(" ", line).strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    return text or None


def _list(value):
    return value if isinstance(value, list) else []


def _dict(value):
    return value if isinstance(value, dict) else {}


def _urls(values):
    return [refs.absolute(v) for v in _list(values) if _str(v)]


def _measure(value):
    """"314.8 mm" / "1.17 kg" / "1237.9919 cm³" -> {"value": 314.8, "unit": "mm"}."""
    value = _str(value)
    if not value:
        return None
    match = re.match(r"^(-?[0-9]+(?:\.[0-9]+)?)\s*([^\d\s].*)?$", value)
    if not match:
        return {"value": None, "unit": None, "text": value}
    return {"value": _float(match.group(1)), "unit": _str(match.group(2))}


def _snake(name):
    out = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", str(name))
    out = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", out)
    return out.lower()


# ---- product ----------------------------------------------------------------------

def _brand(raw):
    raw = _dict(raw)
    name = _str(raw.get("name"))
    if not name:
        return None
    return {
        "name": name,
        "slug": _str(raw.get("seoPath")),
        "link": refs.brand_link(_str(raw.get("seoPath"))),
        "logo": refs.absolute(raw.get("logo") or raw.get("logoUrl")),
    }


def _images(raw):
    raw = _dict(raw)
    full = _urls(raw.get("full"))
    three_sixty = _dict(raw.get("threeSixty"))
    return {
        "full": full,
        "preview": _urls(raw.get("preview")),
        "thumbnails": _urls(raw.get("thumb")),
        "three_sixty": _urls(three_sixty.get("full")),
        "view_360": _urls(raw.get("view360")),
    }


def _attachments(raw):
    out = []
    for item in _list(raw):
        item = _dict(item)
        link = refs.absolute(item.get("url"))
        if link:
            out.append({"name": _str(item.get("name")), "link": link})
    return out


def _category_ref(raw):
    raw = _dict(raw)
    path = _str(raw.get("url") or raw.get("seoPath"))
    return {
        "id": _str(raw.get("id") or raw.get("webId")),
        "name": _str(raw.get("title") or raw.get("name")),
        "path": path,
        "link": refs.category_link(path),
    }


def _breadcrumb(raw):
    raw = _dict(raw)
    path = _str(raw.get("url") or raw.get("seoPath"))
    return {"name": _str(raw.get("title") or raw.get("name")), "path": path, "link": refs.category_link(path)}


def _variant(raw, current_sku):
    raw = _dict(raw)
    sku = _str(raw.get("sku"))
    images = _images(raw.get("images"))
    return {
        "sku": sku,
        "link": refs.absolute(raw.get("seoUrl")) or refs.product_link(sku=sku),
        "attributes": {str(k): _str(v) for k, v in _dict(raw.get("identifyingAttributes")).items()},
        "image": (images["preview"] or images["full"] or images["thumbnails"] or [None])[0],
        "is_current": bool(sku and sku == current_sku),
    }


def _accessory(raw):
    raw = _dict(raw)
    images = _images(raw.get("images"))
    category = _dict(raw.get("category"))
    return {
        "sku": _str(raw.get("sku")),
        "name": _str(raw.get("name")),
        "link": refs.absolute(raw.get("seoPath")),
        "image": (images["preview"] or images["full"] or [None])[0],
        "product_type": _str(raw.get("productType")),
        "is_ranged_online": _bool(raw.get("rangedOnline")),
        "category": {
            "id": _str(category.get("id")), "name": _str(category.get("name")),
            "path": _str(category.get("seoPath")), "link": refs.category_link(_str(category.get("seoPath"))),
        } if category else None,
        "order": _int(raw.get("order")),
    }


def _warranty_option(raw):
    raw = _dict(raw)
    return {
        "sku": _str(raw.get("sku")),
        "name": _str(raw.get("name")),
        "type": _str(raw.get("type")),
        "product_type": _str(raw.get("productType")),
        "description": _text(raw.get("description")),
    }


def _specifications(raw):
    out = []
    for group in _list(raw):
        group = _dict(group)
        attrs = [{"name": _str(a.get("name")), "value": _str(a.get("value"))}
                 for a in _list(group.get("attributes")) if isinstance(a, dict) and _str(a.get("name"))]
        if attrs:
            out.append({"group": _str(group.get("group")), "attributes": attrs})
    return out


def parse_price(raw):
    """One entry of /prices/<skus> ({price, gstRate, tax, hasBusinessPrice},
    cents) -> the public pricing block."""
    raw = _dict(raw)
    if not raw:
        return None
    return {
        "price": _dollars(raw.get("price")),
        "currency": CURRENCY,
        "gst_rate": _float(raw.get("gstRate")),
        "gst_amount": _dollars(raw.get("tax")),
        "has_business_price": _bool(raw.get("hasBusinessPrice")),
    }


def parse_prices(raw, skus):
    """/prices/A,B -> [{sku, price, ...}] in the requested order; a SKU the
    site does not price comes back with null price (the key is absent)."""
    raw = _dict(raw)
    out = []
    for sku in skus:
        entry = parse_price(raw.get(sku))
        out.append({"sku": sku, **(entry or {"price": None, "currency": CURRENCY, "gst_rate": None,
                                               "gst_amount": None, "has_business_price": None})})
    return out


def parse_review_statistics(raw):
    """Bazaarvoice statistics.json -> {sku: {average, count, questions_count,
    answers_count}}."""
    out = {}
    for item in _list(_dict(raw).get("Results")):
        stats = _dict(_dict(item).get("ProductStatistics"))
        sku = _str(stats.get("ProductId"))
        if not sku:
            continue
        reviews = _dict(stats.get("ReviewStatistics"))
        qa = _dict(stats.get("QAStatistics"))
        average = _float(reviews.get("AverageOverallRating"))
        out[sku] = {
            "average": round(average, 2) if average is not None else None,
            "count": _int(reviews.get("TotalReviewCount")) or 0,
            "scale": _int(reviews.get("OverallRatingRange")) or 5,
            "questions_count": _int(qa.get("TotalQuestionCount")) or 0,
            "answers_count": _int(qa.get("TotalAnswerCount")) or 0,
        }
    return out


def parse_review_summary(raw):
    """Bazaarvoice display summary -> the star distribution + recommended
    split the product page shows; None when the product has no reviews."""
    raw = _dict(raw)
    summary = _dict(raw.get("reviewSummary"))
    questions = _dict(raw.get("questionSummary"))
    primary = _dict(summary.get("primaryRating"))
    count = _int(summary.get("numReviews")) or 0
    distribution = {}
    for item in _list(primary.get("distribution")):
        item = _dict(item)
        key = _int(item.get("key"))
        if key is not None:
            distribution[str(key)] = _int(item.get("count")) or 0
    recommended = {"yes": 0, "no": 0}
    for item in _list(_dict(summary.get("recommended")).get("distribution")):
        item = _dict(item)
        recommended["yes" if item.get("key") is True else "no"] = _int(item.get("count")) or 0
    average = _float(primary.get("average"))
    return {
        "average": round(average, 2) if average is not None else None,
        "count": count,
        "scale": _int(primary.get("ratingRange")) or 5,
        "distribution": distribution or None,
        "recommended_count": recommended["yes"],
        "not_recommended_count": recommended["no"],
        "questions_count": _int(questions.get("numQuestions")) or 0,
        "answers_count": _int(questions.get("numAnswers")) or 0,
    }


def _price_drop(attrs):
    drop_type = _str(attrs.get("priceDroppedType"))
    start, end = _str(attrs.get("priceDroppedStartDate")), _str(attrs.get("priceDroppedEndDate"))
    if not (drop_type or start or end):
        return None
    return {"type": drop_type, "start_date": start, "end_date": end}


def parse_product(raw, price=None, reviews=None):
    """catalogue-app /products/<SKU> (+ its /prices entry and the
    Bazaarvoice summary) -> the public product record."""
    raw = _dict(raw)
    sku = _str(raw.get("sku"))
    attrs = {}
    for item in _list(raw.get("attributes")):
        item = _dict(item)
        key = _str(item.get("id"))
        if key:
            attrs[key] = item.get("value")
    description = _dict(raw.get("description"))
    ranged = _dict(raw.get("ranged"))
    review = _dict(raw.get("review"))
    images = _images(raw.get("images"))
    attachments = _dict(raw.get("attachments"))
    family = [_variant(v, sku) for v in _list(raw.get("family"))]
    url_keyword = _str(raw.get("urlKeyword"))
    ribbon = _str(raw.get("ribbon"))
    pricing = parse_price(price) or {"price": None, "currency": CURRENCY, "gst_rate": None,
                                     "gst_amount": None, "has_business_price": None}
    pricing.update({
        "everyday_price": _money_str(raw.get("edlpPrice") or attrs.get("edlpPrice")),
        "is_gst_exempt": _bool(attrs.get("gstExempt")),
        "price_drop": _price_drop(attrs),
    })
    rating_average = _float(review.get("averageRating"))
    rating = {
        "average": round(rating_average, 2) if rating_average is not None else None,
        "count": _int(review.get("count")) or 0,
        "scale": _int(review.get("range")) or 5,
    }
    if reviews:
        rating = {**rating, **{k: v for k, v in reviews.items() if v is not None}}
    return {
        "sku": sku,
        "name": _str(raw.get("name")),
        "short_name": _str(attrs.get("shortProductTitle")),
        "link": refs.absolute(raw.get("seoPath")) or refs.product_link(url_keyword, sku),
        "brand": _brand(raw.get("brand")),
        "product_type": _str(raw.get("productType")),
        "status": _str(attrs.get("status")),
        "promo_label": PROMO_LABELS.get(ribbon, ribbon) if ribbon else None,
        "colour": _str(attrs.get("colour")),
        "pricing": pricing,
        "description": {
            "short": _text(description.get("shortDescription")),
            "long": _text(description.get("longDescription")),
            "meta": _str(raw.get("descriptionMeta")),
        },
        "features": [_text(f) for f in _list(raw.get("fab")) if _text(f)],
        "specifications": _specifications(raw.get("specs")),
        "identifiers": {
            "gtin": _str(raw.get("gtin") or attrs.get("gtin")),
            "case_gtin": _str(attrs.get("caseGTIN")),
            "manufacturer_part_number": _str(raw.get("manufacturerPartNumber") or attrs.get("manufacturerPartNumber")),
            "model_number": _str(attrs.get("modelNumber")),
            "manufacturer": _str(attrs.get("manufacturer")),
            "product_family_code": _str(attrs.get("productFamilyCode")),
            "parent_product_id": _str(attrs.get("parentProductId")),
            "merchandise_category": _str(attrs.get("merchCat")),
        },
        "images": {"primary": refs.absolute(raw.get("image")) or (images["full"] or [None])[0], **images},
        "videos": _attachments(attachments.get("video")),
        "documents": _attachments(attachments.get("doc")),
        "variants": {
            "attributes": {str(k): [_str(x) for x in _list(v)] for k, v in _dict(raw.get("familyAttrs")).items()},
            "count": len(family),
            "options": family,
        },
        "categories": [_category_ref(c) for c in _list(raw.get("category"))],
        "breadcrumbs": [_breadcrumb(b) for b in _list(raw.get("breadcrumbs"))],
        "accessories": [_accessory(a) for a in _list(raw.get("accessories"))],
        "substitutes": [_str(s) for s in _list(raw.get("substitutes")) if _str(s)],
        "warranty_options": [_warranty_option(o) for o in _list(raw.get("productOptions"))],
        "warranty": _str(attrs.get("warranty")),
        "rating": rating,
        "ranging": {
            "is_ranged_online": _bool(raw.get("rangedOnline")) if raw.get("rangedOnline") is not None else _bool(ranged.get("online")),
            "is_ranged_in_store": _bool(raw.get("rangedRetail")) if raw.get("rangedRetail") is not None else _bool(ranged.get("inStore")),
            "is_published": _bool(raw.get("published")),
            "is_preorder": _bool(raw.get("preorderProduct")),
            "is_preorder_available": _bool(raw.get("preorderAvailable")),
            "sales_channel": _str(attrs.get("rangedChannel")),
            "is_loyalty_eligible": _bool(attrs.get("loyaltyEligibleProduct")),
        },
        "shipping": {
            "delivery_min_days": _int(attrs.get("deliveryMinDays")),
            "delivery_max_days": _int(attrs.get("deliveryMaxDays")),
            "has_express_delivery": _bool(attrs.get("expressDelivery")),
            "delivery_method": _str(attrs.get("deliveryMethod")),
            "contains_lithium_batteries": _bool(attrs.get("dangerousLithium")),
            "payment_exclusions": [_str(x) for x in _list(raw.get("paymentExclusion")) if _str(x)],
            "delivery_method_exclusions": [_str(x) for x in _list(raw.get("deliveryMethodExclusion")) if _str(x)],
            "returns_window": _str(attrs.get("marketplaceReturnsWindow")),
        },
        "packaging": {
            "unit_of_measure": _str(attrs.get("sellableUnitOfMeasure")),
            "items_per_unit": _int(raw.get("itemsPerUnit")),
            "items_per_unit_description": _str(raw.get("itemsPerUnitDesc")),
            "total_units": _int(raw.get("totalUnits")),
            "units_per_pack": _int(attrs.get("unitsPerPack")),
            "pack_quantity": _int(attrs.get("packQuantity")),
            "case_quantity": _int(attrs.get("caseQuantity")),
            "weight": _measure(attrs.get("weight")),
            "width": _measure(attrs.get("width")),
            "height": _measure(attrs.get("height")),
            "depth": _measure(attrs.get("depth")),
            "package": {
                "weight": _measure(attrs.get("retailPackageWeight")),
                "width": _measure(attrs.get("retailPackageWidth")),
                "height": _measure(attrs.get("retailPackageHeight")),
                "length": _measure(attrs.get("retailPackageLength")),
                "volume": _measure(attrs.get("retailPackageVolume")),
            },
        },
        "badges": {
            "warranty_logo": refs.absolute(raw.get("warrantyLogoImage")),
            "environment_logos": _urls(raw.get("environmentLogoImages")),
            "safety_logos": _urls(raw.get("safetyLogoPdpImages")) or _urls(raw.get("safetyLogoFabImages")),
        },
        "web_hierarchy": _str(raw.get("webHierarchy")),
        "created_at": _str(attrs.get("erpCreateDate")),
    }


# ---- Algolia listings -------------------------------------------------------------

# Hit keys that are either lifted into named fields below or internal
# ranking / hierarchy plumbing; everything else is a spec attribute the
# index carries for that category (displaySize, ramInstalledSize, ...).
_HIT_KNOWN = {
    "sku", "objectID", "name", "brand", "price", "image", "seoPath", "urlKeyword", "rating", "reviewCount",
    "published", "rangedOnline", "rangedRetail", "status", "productType", "clearanceOnline", "dinkusNew",
    "dinkusForDisplay", "descriptionShort", "gtin", "manufacturerPartNumber", "colour", "erpCreateDate",
    "unitsPerPack", "substitutes", "availState", "availability", "categories", "categoriesLeafToRoot",
    "up1Category", "leafCategory", "categorySeoPaths", "catPaths", "leafCatPath", "up1CatPath",
    "pphCategoryId", "merchCat", "configurableType", "productMerchHierFolderPath", "productWebHierFolderPath",
    "productRankBusiness", "productRankPersonal", "productRankBusinessOverride", "productRankOverallOverride",
    "productRankPersonalOverride", "productRankOverall", "productRankByClass", "productSearchRank",
    "_highlightResult", "_snippetResult", "_rankingInfo", "_distinctSeqID", "priceGroup",
    "customCatalogueInclusions", "customCatalogueExclusions", "productSearchKeywords", "categorySearchKeywords",
}


def _hit_categories(hit):
    paths = [_str(p) for p in _list(hit.get("categorySeoPaths"))]
    names = [_str(n) for n in _list(hit.get("leafCategory"))]
    out = []
    for index, path in enumerate(paths):
        if not path:
            continue
        name = names[index] if index < len(names) and len(names) == len(paths) else None
        out.append({"name": name or path.rsplit("/", 1)[-1].replace("-", " ").title(),
                    "path": path, "link": refs.category_link(path)})
    return out


def parse_hit(hit):
    """One Algolia product hit -> the listing card."""
    hit = _dict(hit)
    sku = _str(hit.get("sku") or hit.get("objectID"))
    url_keyword = _str(hit.get("urlKeyword"))
    dinkus = _str(hit.get("dinkusForDisplay"))
    states = [_str(x) for x in _list(hit.get("availState") or hit.get("availability")) if _str(x)]
    attributes = {}
    for key, value in hit.items():
        if key in _HIT_KNOWN or key.startswith("_") or value in (None, "", []):
            continue
        attributes[_snake(key)] = value
    return {
        "sku": sku,
        "name": _str(hit.get("name")),
        "link": refs.absolute(hit.get("seoPath")) or refs.product_link(url_keyword, sku),
        "brand": _str(hit.get("brand")),
        "price": _dollars(hit.get("price")),
        "currency": CURRENCY,
        "image": refs.absolute(hit.get("image")),
        "rating": {"average": _rating_from_50(hit.get("rating")), "count": _int(hit.get("reviewCount")) or 0, "scale": 5},
        "promo_label": PROMO_LABELS.get(dinkus, dinkus) if dinkus else None,
        "is_clearance": _bool(hit.get("clearanceOnline")),
        "is_new": _bool(hit.get("dinkusNew")),
        "status": _str(hit.get("status")),
        "product_type": _str(hit.get("productType")),
        "colour": _str(hit.get("colour")),
        "description_short": _str(hit.get("descriptionShort")),
        "gtin": _str(hit.get("gtin")),
        "manufacturer_part_number": _str(hit.get("manufacturerPartNumber")),
        "units_per_pack": _int(hit.get("unitsPerPack")),
        "categories": _hit_categories(hit),
        "availability": {
            "is_ranged_online": _bool(hit.get("rangedOnline")),
            "is_ranged_in_store": _bool(hit.get("rangedRetail")),
            "is_published": _bool(hit.get("published")),
            "states": states,
        },
        "substitutes": [_str(s) for s in _list(hit.get("substitutes")) if _str(s)],
        "attributes": attributes,
        "created_at": _date_from_ms(hit.get("erpCreateDate")),
    }


def _facet_values(raw, transform=None):
    out = []
    for value, count in _dict(raw).items():
        out.append({"value": transform(value) if transform else value, "count": _int(count) or 0})
    return out


def parse_facets(result):
    """The facets block of a listing: brands, categories, colours, rating
    and state counts, clearance split, and the price range of the result
    set (facets_stats, cents -> dollars)."""
    result = _dict(result)
    facets = _dict(result.get("facets"))
    stats = _dict(_dict(result.get("facets_stats")).get("price"))
    ratings = []
    for value, count in _dict(facets.get("rating")).items():
        ratings.append({"value": _rating_from_50(value), "count": _int(count) or 0})
    ratings.sort(key=lambda r: (r["value"] is None, r["value"]), reverse=True)
    categories = [{"path": path, "link": refs.category_link(path), "count": _int(count) or 0}
                  for path, count in _dict(facets.get("categorySeoPaths")).items()]
    clearance = _dict(facets.get("clearanceOnline"))
    return {
        "brands": _facet_values(facets.get("brand")),
        "categories": categories,
        "colours": _facet_values(facets.get("colour")),
        "ratings": ratings,
        "states": _facet_values(facets.get("availState")),
        "clearance_count": _int(clearance.get("true")) or 0,
        "price_range": {
            "min": _dollars(stats.get("min")), "max": _dollars(stats.get("max")),
            "average": _dollars(stats.get("avg")), "currency": CURRENCY,
        } if stats else None,
    }


def parse_listing(result, page):
    """One Algolia result page -> {products, facets, pagination}. Algolia
    caps any query at 1,000 hits (paginationLimitedTo) and `nbPages`
    already reflects it, so total_pages is honest; a page past the end is
    an empty page."""
    result = _dict(result)
    hits = [parse_hit(h) for h in _list(result.get("hits"))]
    per_page = _int(result.get("hitsPerPage")) or 24
    total = _int(result.get("nbHits")) or 0
    return {
        "products": hits,
        "facets": parse_facets(result),
        "pagination": {
            "page": page,
            "items_per_page": per_page,
            "total_pages": _int(result.get("nbPages")) or 0,
            "total_count": total,
        },
    }


def parse_suggestions(result):
    """The query-suggestions index -> [{query, popularity, result_count,
    top_categories}]."""
    out = []
    for hit in _list(_dict(result).get("hits")):
        hit = _dict(hit)
        query = _str(hit.get("query") or hit.get("objectID"))
        if not query:
            continue
        index_block = next((v for k, v in hit.items() if k.startswith("prod-product-wc") and isinstance(v, dict)), {})
        exact = _dict(_dict(_dict(index_block.get("facets")).get("exact_matches")))
        categories = [{"name": _str(c.get("value")), "count": _int(c.get("count")) or 0}
                      for c in _list(exact.get("leafCategory")) if isinstance(c, dict) and _str(c.get("value"))]
        out.append({
            "query": query,
            "link": refs.search_link(query),
            "popularity": _int(hit.get("popularity")),
            "result_count": _int(index_block.get("exact_nb_hits")),
            "top_categories": categories,
        })
    return out


# ---- categories -------------------------------------------------------------------

def _category_node(raw, depth=0):
    raw = _dict(raw)
    path = _str(raw.get("seoPath"))
    children = [_category_node(c, depth + 1) for c in _list(raw.get("children"))]
    node = {
        "name": _str(raw.get("name")),
        "path": path,
        "link": refs.category_link(path),
        "level": depth + 1,
    }
    for key in ("id", "webId"):
        if raw.get(key):
            node["id"] = _str(raw.get(key))
            break
    if raw.get("title"):
        node["title"] = _str(raw.get("title"))
    if raw.get("shortDescription"):
        node["short_description"] = _text(raw.get("shortDescription"))
    if raw.get("thumbnail"):
        node["thumbnail"] = refs.absolute(raw.get("thumbnail"))
    node["children"] = children
    return node


def parse_category_tree(raw):
    """/categories -> the nested tree (name / path / link / level / children)."""
    return [_category_node(c) for c in _list(raw)]


def _count_nodes(nodes):
    return sum(1 + _count_nodes(n.get("children") or []) for n in nodes)


def parse_category(raw):
    """/categories/<seoPath> -> metadata, breadcrumbs and children."""
    raw = _dict(raw)
    path = _str(raw.get("seoPath"))
    children = [_category_node(c) for c in _list(raw.get("children"))]
    return {
        "id": _str(raw.get("id") or raw.get("webId")),
        "name": _str(raw.get("name")),
        "path": path,
        "link": refs.category_link(path),
        "title": _str(raw.get("title")),
        "description": _text(raw.get("description")),
        "short_description": _text(raw.get("shortDescription")),
        "thumbnail": refs.absolute(raw.get("thumbnail")),
        "breadcrumbs": [_breadcrumb(b) for b in _list(raw.get("breadcrumbs"))],
        "children": children,
        "children_count": len(children),
    }


# ---- brands -----------------------------------------------------------------------

def parse_brand(raw):
    raw = _dict(raw)
    slug = _str(raw.get("seoPath"))
    return {
        "id": _str(raw.get("id")),
        "name": _str(raw.get("name")),
        "slug": slug,
        "link": refs.brand_link(slug),
        "logo": refs.absolute(raw.get("logoUrl") or raw.get("logo")),
        "description": _text(raw.get("description")),
        "meta_description": _str(raw.get("metaDescription")),
        "campaign_link": refs.absolute(raw.get("sponsoredPageUrl")),
        "is_published": _bool(raw.get("published")),
    }


def parse_brands(raw):
    return [parse_brand(b) for b in _list(raw) if _dict(b).get("name")]


# ---- stores -----------------------------------------------------------------------

def _address(raw):
    raw = _dict(raw)
    return {
        "street": _str(raw.get("street")),
        "located_in": _str(raw.get("locatedIn")),
        "suburb": _str(raw.get("suburb")),
        "postcode": _str(raw.get("postCode") or raw.get("postcode")),
        "state": _str(raw.get("state")),
    }


def _hours(raw):
    return [{"day": _str(h.get("dayOfWeek")), "open": _str(h.get("open")), "close": _str(h.get("close")),
             **({"date": _str(h.get("date"))} if _dict(h).get("date") else {})}
            for h in _list(raw) if isinstance(h, dict)]


def _store_link(store_id, address, name):
    return refs.store_link(store_id, address.get("state"), name)


def parse_store(raw):
    """/stores/<id> (or a /stores/?postCode= entry) -> the full store record."""
    raw = _dict(raw)
    store_id = _str(raw.get("id"))
    address = _address(raw.get("address"))
    location = _dict(raw.get("location"))
    contact = _dict(raw.get("contact"))
    services = {_snake(k): _bool(v) for k, v in _dict(raw.get("services")).items()}
    distance = _float(location.get("distance"))
    return {
        "id": store_id,
        "name": _str(raw.get("name")),
        "link": _store_link(store_id, address, _str(raw.get("name"))),
        "status": _str(raw.get("status")),
        "opening_date": _str(raw.get("openingDate")),
        "address": address,
        "location": {
            "latitude": _float(location.get("latitude") or location.get("lat")),
            "longitude": _float(location.get("longitude") or location.get("lng")),
            "distance_km": round(distance, 2) if distance is not None else None,
        },
        "contact": {
            "phone": _str(contact.get("phone") or raw.get("phone")),
            "fax": _str(contact.get("fax")),
            "email": _str(contact.get("email")),
        },
        "opening_hours": _hours(raw.get("openingHours")),
        "exception_hours": _hours(raw.get("exceptionHours")),
        "services": services or None,
        "notice": _str(raw.get("priorityNotificationText")),
        "activities": _text(_dict(raw.get("messages")).get("activities")),
        "partner_id": _str(raw.get("partnerId")),
    }


def parse_store_card(raw):
    """A /stores (by state) entry -> the short card."""
    raw = _dict(raw)
    store_id = _str(raw.get("id"))
    address = _address(raw.get("address"))
    return {
        "id": store_id,
        "name": _str(raw.get("name")),
        "link": _store_link(store_id, address, _str(raw.get("name"))),
        "address": address,
        "phone": _str(raw.get("phone") or _dict(raw.get("contact")).get("phone")),
    }


def parse_stores_by_state(raw):
    """/stores -> {state: [card]} in a stable state order."""
    raw = _dict(raw)
    out = {}
    for state in list(refs.AU_STATES) + [s for s in raw if s not in refs.AU_STATES]:
        if state in raw:
            out[state] = [parse_store_card(s) for s in _list(raw.get(state))]
    return out


def parse_stores(raw):
    """/stores/?postCode= -> [store] nearest first (distance in km)."""
    return [parse_store(s) for s in _list(raw) if isinstance(s, dict) and s.get("id")]


def parse_location_by_coordinates(raw):
    data = _dict(_dict(raw).get("data"))
    address = _dict(_dict(data.get("accountDeliveryLocationByCoordinates")).get("deliveryAddress"))
    if not address.get("postcode"):
        return None
    return {"postcode": _str(address.get("postcode")), "suburb": _str(address.get("suburb")),
            "state": _str(address.get("state"))}


def parse_locations(raw):
    """/locations/?location= -> [{suburb, postcode, state}]."""
    return [{"suburb": _str(l.get("suburb")), "postcode": _str(l.get("postcode")), "state": _str(l.get("state"))}
            for l in _list(raw) if isinstance(l, dict) and l.get("postcode")]


# ---- availability -----------------------------------------------------------------

def _availability_leg(raw):
    raw = _dict(raw)
    if not raw:
        return None
    quantity = _int(raw.get("quantity"))
    out = {
        "is_available": bool(quantity) if quantity is not None else None,
        "quantity": quantity,
        "available_date": _iso(raw.get("availableDate")),
        "available_relative": _str(raw.get("relativeAvailableDate")),
    }
    if "quickCollectAvailable" in raw:
        out["is_quick_collect_available"] = _bool(raw.get("quickCollectAvailable"))
    return out


def parse_availability(raw, sku, store_id, postcode, quantity):
    """product-catalogue GetAvailability -> per-store stock; None when the
    product is unknown ({"data": {"product": null}}). An unknown store
    answers {"errors"} with an empty store block, which comes back as a
    record with store.status null and every leg null."""
    body = _dict(raw)
    product = _dict(body.get("data")).get("product")
    if not isinstance(product, dict):
        return None
    availability = _dict(product.get("availability"))
    store = _dict(product.get("store"))
    ranged = _dict(product.get("ranged"))
    errors = [_str(e.get("message")) for e in _list(body.get("errors")) if isinstance(e, dict)]
    store_known = bool(_str(store.get("name")))
    return {
        "sku": sku,
        "product_type": _str(product.get("productType")),
        "requested_quantity": quantity,
        "postcode": postcode,
        "store": {
            "id": _str(store.get("id")) or store_id,
            "name": _str(store.get("name")),
            "status": _str(store.get("status")),
            "postcode": _str(store.get("postcode")),
            "state": _str(store.get("state")),
            "link": refs.store_link(_str(store.get("id")) or store_id, _str(store.get("state")), _str(store.get("name"))),
            "is_known": store_known,
        },
        "is_ranged_online": _bool(ranged.get("online")),
        "is_ranged_in_store": _bool(ranged.get("inStore")),
        "click_and_collect": _availability_leg(availability.get("clickAndCollect")),
        "in_store": _availability_leg(availability.get("inStore")),
        "delivery": _availability_leg(availability.get("deliverToDoor")),
        "errors": [e for e in errors if e] or None,
    }


# ---- reviews / questions ----------------------------------------------------------

def _feedback(raw):
    raw = _dict(raw)
    return {
        "helpful": _int(raw.get("TotalPositiveFeedbackCount")) or 0,
        "unhelpful": _int(raw.get("TotalNegativeFeedbackCount")) or 0,
        "total": _int(raw.get("TotalFeedbackCount")) or 0,
    }


def _photos(raw):
    out = []
    for photo in _list(raw):
        sizes = _dict(_dict(photo).get("Sizes"))
        pick = _dict(sizes.get("large") or sizes.get("normal") or next(iter(sizes.values()), {}))
        link = _str(pick.get("Url"))
        if link:
            out.append({"id": _str(_dict(photo).get("Id")), "link": link,
                        "thumbnail": _str(_dict(sizes.get("thumbnail")).get("Url"))})
    return out


def _videos(raw):
    out = []
    for video in _list(raw):
        video = _dict(video)
        link = _str(video.get("VideoUrl") or video.get("VideoHost"))
        if link:
            out.append({"link": link, "thumbnail": _str(video.get("VideoThumbnailUrl")), "caption": _str(video.get("Caption"))})
    return out


def _badges(raw):
    return [_str(_dict(b).get("Id") or k) for k, b in _dict(raw).items() if _str(_dict(b).get("Id") or k)]


def _context(raw):
    return {str(k): _str(_dict(v).get("Value")) for k, v in _dict(raw).items()} or None


def parse_review(raw):
    raw = _dict(raw)
    secondary = {str(k): _int(_dict(v).get("Value")) for k, v in _dict(raw.get("SecondaryRatings")).items()}
    responses = []
    for item in _list(raw.get("ClientResponses")):
        item = _dict(item)
        text = _text(item.get("Response"))
        if text:
            responses.append({"department": _str(item.get("Department")), "text": text,
                              "date": _iso(item.get("Date")), "source": _str(item.get("ResponseSource"))})
    return {
        "id": _str(raw.get("Id")),
        "title": _str(raw.get("Title")),
        "text": _str(raw.get("ReviewText")),
        "rating": _int(raw.get("Rating")),
        "rating_scale": _int(raw.get("RatingRange")) or 5,
        "is_recommended": _bool(raw.get("IsRecommended")),
        "secondary_ratings": secondary or None,
        "pros": _str(raw.get("Pros")),
        "cons": _str(raw.get("Cons")),
        "author": {
            "nickname": _str(raw.get("UserNickname")),
            "id": _str(raw.get("AuthorId")),
            "location": _str(raw.get("UserLocation")),
            "badges": _badges(raw.get("Badges")),
        },
        "purchase_context": _context(raw.get("ContextDataValues")),
        "feedback": _feedback(raw),
        "helpfulness": _float(raw.get("Helpfulness")),
        "photos": _photos(raw.get("Photos")),
        "videos": _videos(raw.get("Videos")),
        "brand_responses": responses,
        "comments_count": _int(raw.get("TotalCommentCount")) or 0,
        "is_featured": _bool(raw.get("IsFeatured")),
        "is_ratings_only": _bool(raw.get("IsRatingsOnly")),
        "is_syndicated": _bool(raw.get("IsSyndicated")),
        "moderation_status": _str(raw.get("ModerationStatus")),
        "locale": _str(raw.get("ContentLocale")),
        "product": {"sku": _str(raw.get("ProductId")), "name": _str(raw.get("OriginalProductName"))},
        "submitted_at": _iso(raw.get("SubmissionTime")),
        "last_modified_at": _iso(raw.get("LastModificationTime")),
    }


def _product_review_statistics(raw, sku):
    """The Includes.Products[sku].ReviewStatistics block of a reviews page."""
    product = _dict(_dict(_dict(_dict(raw).get("Includes")).get("Products")).get(sku))
    stats = _dict(product.get("ReviewStatistics"))
    if not stats:
        return None
    distribution = {}
    for item in _list(stats.get("RatingDistribution")):
        item = _dict(item)
        key = _int(item.get("RatingValue"))
        if key is not None:
            distribution[str(key)] = _int(item.get("Count")) or 0
    secondary = {}
    for key, value in _dict(stats.get("SecondaryRatingsAverages")).items():
        avg = _float(_dict(value).get("AverageRating"))
        secondary[str(key)] = round(avg, 2) if avg is not None else None
    average = _float(stats.get("AverageOverallRating"))
    return {
        "average": round(average, 2) if average is not None else None,
        "count": _int(stats.get("TotalReviewCount")) or 0,
        "scale": _int(stats.get("OverallRatingRange")) or 5,
        "distribution": distribution or None,
        "recommended_count": _int(stats.get("RecommendedCount")) or 0,
        "not_recommended_count": _int(stats.get("NotRecommendedCount")) or 0,
        "ratings_only_count": _int(stats.get("RatingsOnlyReviewCount")) or 0,
        "helpful_votes": _int(stats.get("HelpfulVoteCount")) or 0,
        "secondary_averages": secondary or None,
        "first_review_at": _iso(stats.get("FirstSubmissionTime")),
        "last_review_at": _iso(stats.get("LastSubmissionTime")),
    }


def parse_reviews(raw, sku, page, per_page):
    """Bazaarvoice reviews.json -> {reviews, summary, pagination}."""
    raw = _dict(raw)
    total = _int(raw.get("TotalResults")) or 0
    reviews = [parse_review(r) for r in _list(raw.get("Results")) if isinstance(r, dict)]
    return {
        "sku": sku,
        "summary": _product_review_statistics(raw, sku),
        "reviews": reviews,
        "pagination": {
            "page": page,
            "items_per_page": per_page,
            "total_pages": math.ceil(total / per_page) if per_page else 0,
            "total_count": total,
        },
    }


def parse_answer(raw):
    raw = _dict(raw)
    return {
        "id": _str(raw.get("Id")),
        "text": _str(raw.get("AnswerText")),
        "author": {
            "nickname": _str(raw.get("UserNickname")),
            "location": _str(raw.get("UserLocation")),
            "badges": _badges(raw.get("Badges")),
        },
        "is_brand_answer": _bool(raw.get("IsBrandAnswer")),
        "is_staff_answer": "Staff" in _badges(raw.get("Badges")),
        "is_best_answer": _bool(raw.get("IsBestAnswer")),
        "feedback": _feedback(raw),
        "photos": _photos(raw.get("Photos")),
        "submitted_at": _iso(raw.get("SubmissionTime")),
    }


def parse_question(raw, answers_by_id):
    raw = _dict(raw)
    answers = [parse_answer(answers_by_id[a]) for a in _list(raw.get("AnswerIds"))
               if a in answers_by_id and isinstance(answers_by_id[a], dict)]
    return {
        "id": _str(raw.get("Id")),
        "question": _str(raw.get("QuestionSummary")),
        "details": _str(raw.get("QuestionDetails")),
        "author": {
            "nickname": _str(raw.get("UserNickname")),
            "location": _str(raw.get("UserLocation")),
            "badges": _badges(raw.get("Badges")),
        },
        "answers_count": _int(raw.get("TotalAnswerCount")) or 0,
        "has_best_answer": _bool(raw.get("HasBestAnswer")),
        "feedback": _feedback(raw),
        "answers": answers,
        "product": {"sku": _str(raw.get("ProductId"))},
        "submitted_at": _iso(raw.get("SubmissionTime")),
    }


def parse_questions(raw, sku, page, per_page):
    """Bazaarvoice questions.json (Include=Answers) -> {questions, pagination}."""
    raw = _dict(raw)
    total = _int(raw.get("TotalResults")) or 0
    answers = _dict(_dict(raw.get("Includes")).get("Answers"))
    questions = [parse_question(q, answers) for q in _list(raw.get("Results")) if isinstance(q, dict)]
    return {
        "sku": sku,
        "questions": questions,
        "pagination": {
            "page": page,
            "items_per_page": per_page,
            "total_pages": math.ceil(total / per_page) if per_page else 0,
            "total_count": total,
        },
    }


# ---- sitemaps ---------------------------------------------------------------------

_SITEMAP_ENTRY_RE = re.compile(r"<(?:url|sitemap)>(.*?)</(?:url|sitemap)>", re.S)
_SITEMAP_FIELD_RE = re.compile(r"<(loc|lastmod|changefreq|priority)>\s*(.*?)\s*</\1>", re.S)
_STORE_PAGE_RE = re.compile(r"/storepage/(W[0-9]{3})(?:/([A-Z]{2,3})/([^/?#]+))?", re.I)


def parse_sitemap_entries(xml):
    """<urlset> / <sitemapindex> XML -> [{link, last_modified,
    change_frequency, priority}] in document order."""
    out = []
    for block in _SITEMAP_ENTRY_RE.findall(xml or ""):
        fields = {name: html.unescape(value) for name, value in _SITEMAP_FIELD_RE.findall(block)}
        link = _str(fields.get("loc"))
        if not link:
            continue
        out.append({
            "link": link,
            "last_modified": _str(fields.get("lastmod")),
            "change_frequency": _str(fields.get("changefreq")),
            "priority": _float(fields.get("priority")),
        })
    return out


def parse_sitemap_index(xml):
    """sitemap.xml -> [{type, link, last_modified}]."""
    out = []
    for entry in parse_sitemap_entries(xml):
        match = re.search(r"/sitemap-([a-z]+)\.xml", entry["link"])
        out.append({"type": match.group(1) if match else None, "link": entry["link"],
                    "last_modified": entry["last_modified"]})
    return out


def _decorate_sitemap_entry(entry, kind):
    link = entry["link"]
    if kind == "products":
        slug = link.rsplit("/p/", 1)[-1] if "/p/" in link else None
        entry = {"sku": slug.rsplit("-", 1)[-1].upper() if slug else None, "slug": slug, **entry}
    elif kind == "categories":
        entry = {"path": link.split("/c/", 1)[-1].strip("/") if "/c/" in link else None, **entry}
    elif kind == "stores":
        match = _STORE_PAGE_RE.search(link)
        entry = {"id": match.group(1).upper() if match else None,
                 "state": (match.group(2) or "").upper() or None if match else None,
                 "name": match.group(3).replace("-", " ") if match and match.group(3) else None, **entry}
    return entry


def parse_sitemap(xml, kind):
    """One sub-sitemap -> entries with the record key each link carries
    (products: sku + slug; categories: path; stores: id / state / name)."""
    return [_decorate_sitemap_entry(e, kind) for e in parse_sitemap_entries(xml)]
