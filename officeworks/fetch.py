"""Officeworks transport: plain curl_cffi with browser-impersonated TLS. No
browser, no cookies, no tokens. Egress: the pod's own IP
(config.officeworks_proxy(), knob OFFICEWORKS_EXIT = None) — the pod probe
of 2026-10-28 (scrapers-patchright-depl-fdd5b584c-pq7mg) answered 200 on all
13 surfaces from the pod's own Google Cloud IP; AWS WAF only challenges
some exits (a home ISP in India, 1 of 2 datacenter ports) with an HTTP 405
"Human Verification" page, which classifies as Blocked here. A retryable
failure drops the thread's session so the retry starts a fresh connection
(and, with a proxy knob, a fresh exit).

Upstream surfaces (all public, no login):

  * CATALOGUE  GET www.officeworks.com.au/catalogue-app/api/<route> — the
    storefront's own JSON: products/<SKU>, products?sku=A,B, prices/A,B,
    categories, categories/<seoPath>, brands, brands/?seoPath=, stores,
    stores/<id>, stores/?postCode=, locations/?location=. Unknown ids
    answer a real 404 with body "{}".
  * GRAPHQL    POST /facade/product-catalogue (per-store stock:
    GetAvailability) and POST /facade/ow-graphql (lat,lng -> postcode:
    accountDeliveryLocationByCoordinates). HTTP 200 with {"errors"} for a
    bad variable; a missing product is {"data": {"product": null}}.
  * SITEMAP    GET /sitemap.xml index + sitemap-{products,categories,
    stores,content,campaigns}.xml (the products one is 8.7 MB, 40k URLs).
  * ALGOLIA    POST K535CAAWVE-dsn.algolia.net/1/indexes/*/queries with the
    site's public search key (ACL search / listIndexes / settings, read
    from every page's __INITIAL_STATE__.searchConfig). Serves search,
    category, brand, deals and clearance listings + query suggestions.
    Reachable from any IP, so it never goes through the site's proxy.
  * BAZAARVOICE GET api.bazaarvoice.com/data/{reviews,questions,
    statistics}.json with the site's public passkey. Also open from any IP.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  OfficeworksUpstreamError  transport failure / 5xx / odd body  — retryable
  OfficeworksBlocked        403 / 429 / WAF challenge page       — retryable
  OfficeworksBadRequest     upstream 400                         — never retried
  OfficeworksNotFound       404 / unknown SKU, category, store   — never retried
"""
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from officeworks.refs import CATALOGUE_API, SITE

IMPERSONATE = "chrome"
JSON_TIMEOUT = 20
SITEMAP_TIMEOUT = 90      # sitemap-products.xml is 8.7 MB

ALGOLIA_APP_ID = "K535CAAWVE"
ALGOLIA_API_KEY = "8a831febe0110932cfa06ff0e2024b4f"   # the site's public search-only key
ALGOLIA_HOST = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net"
ALGOLIA_PRODUCT_INDEX = "prod-product-wc"              # replicas: -bestmatch-personal, -newest, ...
ALGOLIA_SUGGEST_INDEX = "prod-product-wc-query-suggest"

BAZAARVOICE_HOST = "https://api.bazaarvoice.com"
BAZAARVOICE_PASSKEY = "caPhGpW9jrU4bNWcK3CMF12f4YwXlGWfaTlQKe9K6lay4"   # public display passkey
BAZAARVOICE_API_VERSION = "5.4"

JSON_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": egress.site_accept_language("officeworks"),
    "referer": SITE + "/",
}
GRAPHQL_HEADERS = {**JSON_HEADERS, "content-type": "application/json", "origin": SITE}
XML_HEADERS = {
    "accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
    "accept-language": egress.site_accept_language("officeworks"),
}
ALGOLIA_HEADERS = {
    "x-algolia-application-id": ALGOLIA_APP_ID,
    "x-algolia-api-key": ALGOLIA_API_KEY,
    "content-type": "application/json",
    "accept": "application/json",
    "origin": SITE,
    "referer": SITE + "/",
}


class OfficeworksUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unparseable body — retryable."""


class OfficeworksBlocked(OfficeworksUpstreamError, Blocked):
    """403 / 429 or the AWS WAF "Human Verification" page — retryable."""


class OfficeworksBadRequest(BadRequest):
    """Upstream 400 — never retried."""


class OfficeworksNotFound(NotFound):
    """SKU / category / brand / store / page does not exist — never retried."""


# One session per cheroot worker thread (a curl handle must not be shared
# across threads). `site` sessions carry the egress knob; `open` sessions
# (Algolia, Bazaarvoice) are reachable from any IP and never ride a proxy,
# so a residential knob would not burn paid proxy bytes on them.
_local = threading.local()


def _session(kind="site"):
    store = getattr(_local, "sessions", None)
    if store is None:
        store = _local.sessions = {}
    sess = store.get(kind)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = config.officeworks_proxy() if kind == "site" else None
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        store[kind] = sess
    return sess


def _drop_session(kind="site"):
    """Close the thread's session so a poisoned keep-alive connection (or a
    refused exit) dies and the retry starts fresh."""
    store = getattr(_local, "sessions", None) or {}
    sess = store.pop(kind, None)
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _retrying(fn, kind="site"):
    """Run fn() under the shared retry policy (OfficeworksUpstreamError
    only; NotFound / BadRequest surface immediately)."""
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except OfficeworksUpstreamError as e:
            last = e
            _drop_session(kind)
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def _looks_like_challenge(resp):
    content_type = (resp.headers.get("content-type") or "").lower()
    if "text/html" not in content_type:
        return False
    head = (resp.text or "")[:3000].lower()
    return "human verification" in head or "awswaf" in head or "captcha" in head


def _classify(resp, label):
    """Map an HTTP response to the error taxonomy."""
    status = resp.status_code
    if status == 404:
        raise OfficeworksNotFound(f"{label} not found")
    if status == 400:
        raise OfficeworksBadRequest(resp.text[:200])
    if status in (401, 403, 429) or (status == 405 and _looks_like_challenge(resp)):
        raise OfficeworksBlocked(f"HTTP {status} for {label}")
    if status != 200:
        raise OfficeworksUpstreamError(f"HTTP {status} for {label}")
    if _looks_like_challenge(resp):
        raise OfficeworksBlocked(f"challenge page for {label}")


def _json_body(resp, label):
    try:
        return resp.json()
    except Exception:
        raise OfficeworksUpstreamError(f"non-JSON body for {label}: {(resp.text or '')[:120]!r}")


# ---- catalogue-app JSON -------------------------------------------------------

def catalogue_get(route, label, params=None):
    """GET /catalogue-app/api/<route> -> parsed JSON. 404 -> NotFound."""
    def once():
        try:
            resp = _session().get(CATALOGUE_API + route, params=params,
                                  headers=JSON_HEADERS, timeout=JSON_TIMEOUT)
        except Exception as e:
            raise OfficeworksUpstreamError(f"request failed: {type(e).__name__}: {e}")
        _classify(resp, label)
        return _json_body(resp, label)
    return _retrying(once)


def fetch_product(sku):
    """The full product record (catalogue-app /products/<SKU>)."""
    return catalogue_get(f"/products/{sku}", f"product {sku}")


def fetch_products(skus):
    """Several product records at once (/products?sku=A,B); unknown SKUs are
    simply absent from the list."""
    return catalogue_get("/products", "products", params={"sku": ",".join(skus)})


def fetch_prices(skus):
    """{sku: {price, gstRate, tax, hasBusinessPrice}} in cents; unknown SKUs
    are absent (an all-unknown list answers 200 "{}")."""
    return catalogue_get(f"/prices/{','.join(skus)}", "prices")


def fetch_categories():
    """The whole category tree (name / seoPath / children)."""
    return catalogue_get("/categories", "categories")


def fetch_category(seo_path):
    """One category's metadata, children and breadcrumbs."""
    return catalogue_get(f"/categories/{seo_path}", f"category {seo_path}")


def fetch_brands():
    """Every brand (851 on 2026-10-28) with logo, description, seoPath."""
    return catalogue_get("/brands", "brands")


def fetch_brand(seo_path):
    """[brand] for a seoPath, [] when unknown."""
    return catalogue_get("/brands/", f"brand {seo_path}", params={"seoPath": seo_path})


def fetch_stores():
    """Every store grouped by state ({QLD: [...], VIC: [...], ...})."""
    return catalogue_get("/stores", "stores")


def fetch_store(store_id):
    """One store with hours, exception hours, contact and services."""
    return catalogue_get(f"/stores/{store_id}", f"store {store_id}")


def fetch_stores_by_postcode(postcode, limit=10):
    """Active stores nearest a postcode (the site's own store finder); an
    unknown postcode answers 404, which the caller turns into an empty list."""
    return catalogue_get("/stores/", f"stores near {postcode}",
                         params={"postCode": postcode, "activeOnly": "true", "limit": limit})


def fetch_locations(term):
    """Suburb / postcode suggestions for a free-text term; no match -> 404."""
    return catalogue_get("/locations/", f"locations {term}", params={"location": term})


# ---- GraphQL facades ----------------------------------------------------------

AVAILABILITY_QUERY = """query GetAvailability($sku: String!, $quantity: Int!, $storeId: String!, $postCode: String) {
  product(sku: $sku, quantity: $quantity) {
    productType
    ranged { online inStore }
    availability(storeId: $storeId, postCode: $postCode) {
      clickAndCollect { availableDate relativeAvailableDate quantity quickCollectAvailable }
      inStore { availableDate relativeAvailableDate quantity }
      deliverToDoor { availableDate relativeAvailableDate quantity }
    }
    store(storeId: $storeId) { id name status postcode state }
  }
}"""

LOCATION_BY_COORDINATES_QUERY = """query MyCurrentLocation($long: String!, $lat: String!) {
  accountDeliveryLocationByCoordinates(Coordinates: { long: $long, lat: $lat }) {
    deliveryAddress { postcode state suburb }
  }
}"""


def graphql(path, query, variables, label):
    """POST a GraphQL document to /facade/<path> -> the full {data, errors}
    body (the caller interprets nulls and errors per query)."""
    def once():
        try:
            resp = _session().post(SITE + path, data=json.dumps({"query": query, "variables": variables}),
                                   headers=GRAPHQL_HEADERS, timeout=JSON_TIMEOUT)
        except Exception as e:
            raise OfficeworksUpstreamError(f"request failed: {type(e).__name__}: {e}")
        _classify(resp, label)
        body = _json_body(resp, label)
        if not isinstance(body, dict):
            raise OfficeworksUpstreamError(f"unexpected GraphQL body for {label}")
        return body
    return _retrying(once)


def fetch_availability(sku, store_id, postcode=None, quantity=1):
    return graphql("/facade/product-catalogue", AVAILABILITY_QUERY,
                   {"sku": sku, "quantity": quantity, "storeId": store_id, "postCode": postcode},
                   f"availability {sku} at {store_id}")


def fetch_location_by_coordinates(lat, lng):
    return graphql("/facade/ow-graphql", LOCATION_BY_COORDINATES_QUERY,
                   {"long": str(lng), "lat": str(lat)}, f"location {lat},{lng}")


# ---- sitemaps -----------------------------------------------------------------

def fetch_sitemap(name=None):
    """The sitemap index (name=None) or one sub-sitemap ("products", ...)
    as XML text."""
    path = "/sitemap.xml" if name is None else f"/sitemap-{name}.xml"

    def once():
        try:
            resp = _session().get(SITE + path, headers=XML_HEADERS, timeout=SITEMAP_TIMEOUT)
        except Exception as e:
            raise OfficeworksUpstreamError(f"request failed: {type(e).__name__}: {e}")
        _classify(resp, f"sitemap {name or 'index'}")
        text = resp.text or ""
        if "<urlset" not in text and "<sitemapindex" not in text:
            raise OfficeworksUpstreamError(f"sitemap {name or 'index'} is not XML")
        return text
    return _retrying(once)


# ---- Algolia (open from any IP) -----------------------------------------------

def algolia_query(index_name, params):
    """One query against an index -> its result object (hits, nbHits, facets,
    ...). `params` is the URL-encoded Algolia parameter string."""
    def once():
        body = json.dumps({"requests": [{"indexName": index_name, "params": params}]})
        try:
            resp = _session("open").post(ALGOLIA_HOST + "/1/indexes/*/queries", data=body,
                                         headers=ALGOLIA_HEADERS, timeout=JSON_TIMEOUT)
        except Exception as e:
            raise OfficeworksUpstreamError(f"algolia request failed: {type(e).__name__}: {e}")
        if resp.status_code == 400:
            raise OfficeworksBadRequest(f"search rejected: {resp.text[:200]}")
        if resp.status_code in (401, 403, 429):
            raise OfficeworksBlocked(f"algolia HTTP {resp.status_code}")
        if resp.status_code != 200:
            raise OfficeworksUpstreamError(f"algolia HTTP {resp.status_code}")
        payload = _json_body(resp, "algolia")
        results = payload.get("results") if isinstance(payload, dict) else None
        if not results or not isinstance(results[0], dict):
            raise OfficeworksUpstreamError(f"unexpected algolia body: {resp.text[:120]!r}")
        return results[0]
    return _retrying(once, "open")


# ---- Bazaarvoice (open from any IP) -------------------------------------------

def bazaarvoice_get(resource, params, label):
    """GET /data/<resource>.json -> the body dict. Bazaarvoice answers 200
    with HasErrors for a bad filter, which is a BadRequest here."""
    def once():
        query = {"apiversion": BAZAARVOICE_API_VERSION, "passkey": BAZAARVOICE_PASSKEY, **params}
        try:
            resp = _session("open").get(f"{BAZAARVOICE_HOST}/data/{resource}.json", params=query,
                                        headers={"accept": "application/json"}, timeout=JSON_TIMEOUT)
        except Exception as e:
            raise OfficeworksUpstreamError(f"bazaarvoice request failed: {type(e).__name__}: {e}")
        if resp.status_code in (401, 403, 429):
            raise OfficeworksBlocked(f"bazaarvoice HTTP {resp.status_code} for {label}")
        if resp.status_code != 200:
            raise OfficeworksUpstreamError(f"bazaarvoice HTTP {resp.status_code} for {label}")
        body = _json_body(resp, label)
        if not isinstance(body, dict):
            raise OfficeworksUpstreamError(f"unexpected bazaarvoice body for {label}")
        if body.get("HasErrors"):
            errors = body.get("Errors") or []
            message = "; ".join(str(e.get("Message") or e) for e in errors if e) or "bad request"
            raise OfficeworksBadRequest(f"reviews service: {message}")
        return body
    return _retrying(once, "open")


def fetch_reviews(sku, limit, offset, sort):
    return bazaarvoice_get("reviews", {
        "Filter": f"ProductId:{sku}", "Limit": limit, "Offset": offset, "Sort": sort,
        "Include": "Products", "Stats": "Reviews"}, f"reviews {sku}")


def fetch_questions(sku, limit, offset):
    return bazaarvoice_get("questions", {
        "Filter": f"ProductId:{sku}", "Limit": limit, "Offset": offset,
        "Sort": "SubmissionTime:desc", "Include": "Answers"}, f"questions {sku}")


def fetch_review_statistics(skus):
    """Average rating / review count / Q&A counts for up to ~50 SKUs at once."""
    return bazaarvoice_get("statistics", {
        "filter": "productid:eq:" + ",".join(skus), "stats": "Reviews,Questions",
        "Limit": max(len(skus), 1)}, "review statistics")


def fetch_review_summary(sku):
    """The star distribution + recommended split the product page shows
    (the display API, same passkey)."""
    def once():
        url = (f"{BAZAARVOICE_HOST}/data/display/0.2alpha/product/summary?ApiVersion=5.4"
               f"&Passkey={BAZAARVOICE_PASSKEY}&contentType=reviews,questions"
               f"&reviewDistribution=primaryRating,recommended&rev=0&contentlocale=en*,en_AU"
               f"&productid={sku}")
        try:
            resp = _session("open").get(url, headers={"accept": "application/json"}, timeout=JSON_TIMEOUT)
        except Exception as e:
            raise OfficeworksUpstreamError(f"bazaarvoice request failed: {type(e).__name__}: {e}")
        if resp.status_code in (401, 403, 429):
            raise OfficeworksBlocked(f"bazaarvoice HTTP {resp.status_code} for summary {sku}")
        if resp.status_code != 200:
            raise OfficeworksUpstreamError(f"bazaarvoice HTTP {resp.status_code} for summary {sku}")
        body = _json_body(resp, f"review summary {sku}")
        return body if isinstance(body, dict) else {}
    return _retrying(once, "open")
