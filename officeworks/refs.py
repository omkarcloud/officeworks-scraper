"""Reference resolvers + link builders for /officeworks/*.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url` / `id` pair). Every resolver raises ValueError with a user-facing
message (RefField turns it into a 400).

Identifier shapes (captured 2026-10-28 from the site's own JSON and the
40,035-URL product sitemap):

  * product   SKU, upper-case alphanumeric, 3-12 chars (LOM280BLK,
              ACD5ZSA001, BI2411BE). The product link is
              /shop/officeworks/p/<name-slug>-<sku lower-case>: the last
              hyphen segment of the slug IS the SKU (every sitemap slug has
              one). The catalogue JSON is case-sensitive, so the resolver
              upper-cases.
  * category  seoPath "office-supplies/pens/ballpoint-pens" (lower-case
              slugs joined by "/"); link /shop/officeworks/c/<seoPath>.
  * brand     the brand name ("Logitech", "HP"), its seoPath ("logitech"),
              or a link /shop/officeworks/b/<seoPath> | /brands/<seoPath>.
              Algolia's brand facet matches names case-insensitively; a
              slug is looked up through /catalogue-app/api/brands/?seoPath=
              (officeworks/api.py) when it does not match as a name.
  * store     W + 3 digits (W320); link
              /shop/officeworks/storepage/W320/VIC/Melbourne.
"""
import re
from urllib.parse import unquote, urlparse

SITE = "https://www.officeworks.com.au"
CATALOGUE_API = SITE + "/catalogue-app/api"
PRODUCT_PATH = "/shop/officeworks/p/"
CATEGORY_PATH = "/shop/officeworks/c/"
BRAND_PATH = "/shop/officeworks/b/"
STORE_PATH = "/shop/officeworks/storepage/"
SEARCH_PATH = "/shop/officeworks/search"

SKU_RE = re.compile(r"^[A-Z0-9]{3,12}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CATEGORY_RE = re.compile(r"^[a-z0-9-]+(?:/[a-z0-9-]+)*$")
STORE_RE = re.compile(r"^W[0-9]{3}$")
POSTCODE_RE = re.compile(r"^[0-9]{4}$")
COORDS_RE = re.compile(r"^(-?[0-9]{1,2}(?:\.[0-9]+)?)\s*,\s*(-?[0-9]{1,3}(?:\.[0-9]+)?)$")

_LINK_PRODUCT_RE = re.compile(r"/shop/officeworks/p/([A-Za-z0-9-]+)")
_LINK_CATEGORY_RE = re.compile(r"/shop/officeworks/c/([A-Za-z0-9/-]+)")
_LINK_BRAND_RE = re.compile(r"/(?:shop/officeworks/b|brands|campaigns/brands)/([A-Za-z0-9-]+)")
_LINK_STORE_RE = re.compile(r"/storepage/(W[0-9]{3})", re.I)

AU_STATES = ("NSW", "VIC", "QLD", "SA", "WA", "TAS", "ACT", "NT")
SITEMAP_TYPES = ("products", "categories", "stores", "content", "campaigns")   # /sitemap-<type>.xml


def _is_link(value):
    return value.startswith(("http://", "https://", "//"))


def _site_url(value, what):
    """A pasted link -> its URL, or ValueError when it is another site's."""
    url = value if not value.startswith("//") else "https:" + value
    host = (urlparse(url).hostname or "").lower()
    if not (host == "officeworks.com.au" or host.endswith(".officeworks.com.au")):
        raise ValueError(f"Must be an officeworks.com.au {what} link.")
    return unquote(url)


def resolve_product(value):
    """Bare SKU, product slug, or an officeworks.com.au product link -> SKU."""
    value = (value or "").strip()
    if not value:
        raise ValueError("Must be a SKU (LOM280BLK) or an officeworks.com.au product link.")
    if _is_link(value):
        url = _site_url(value, "product")
        match = _LINK_PRODUCT_RE.search(url)
        if not match:
            raise ValueError("Must be an officeworks.com.au product link "
                             "(https://www.officeworks.com.au/shop/officeworks/p/<slug>).")
        value = match.group(1)
    value = value.strip("/").split("?")[0].split("#")[0]
    if "-" in value:
        value = value.rsplit("-", 1)[-1]
    sku = value.upper()
    if not SKU_RE.match(sku):
        raise ValueError("Must be a SKU (LOM280BLK) or an officeworks.com.au product link.")
    return sku


def resolve_category(value):
    """Category seoPath ("office-supplies/pens") or a category link -> seoPath."""
    value = (value or "").strip()
    if not value:
        raise ValueError("Must be a category path (office-supplies/pens/ballpoint-pens) "
                         "or an officeworks.com.au category link.")
    if _is_link(value):
        url = _site_url(value, "category")
        match = _LINK_CATEGORY_RE.search(url)
        if not match:
            raise ValueError("Must be an officeworks.com.au category link "
                             "(https://www.officeworks.com.au/shop/officeworks/c/<path>).")
        value = match.group(1)
    path = value.strip("/").split("?")[0].split("#")[0].lower()
    if not CATEGORY_RE.match(path):
        raise ValueError("Must be a category path (office-supplies/pens/ballpoint-pens) "
                         "or an officeworks.com.au category link.")
    return path


def resolve_brand(value):
    """Brand name, brand seoPath, or a brand link -> the name / slug as
    typed (officeworks/api.py decides whether it is a name or a slug)."""
    value = (value or "").strip()
    if not value:
        raise ValueError("Must be a brand name (Logitech), its slug (logitech) "
                         "or an officeworks.com.au brand link.")
    if _is_link(value):
        url = _site_url(value, "brand")
        match = _LINK_BRAND_RE.search(url)
        if not match:
            raise ValueError("Must be an officeworks.com.au brand link "
                             "(https://www.officeworks.com.au/shop/officeworks/b/<brand>).")
        value = match.group(1).lower()
    value = value.strip("/").split("?")[0].split("#")[0]
    if len(value) > 80:
        raise ValueError("Brand is too long.")
    return value


def resolve_store(value):
    """Store id (W320) or a store page link -> the id."""
    value = (value or "").strip()
    if not value:
        raise ValueError("Must be a store id (W320) or an officeworks.com.au store link.")
    if _is_link(value):
        url = _site_url(value, "store")
        match = _LINK_STORE_RE.search(url)
        if not match:
            raise ValueError("Must be an officeworks.com.au store link "
                             "(https://www.officeworks.com.au/shop/officeworks/storepage/W320/VIC/Melbourne).")
        value = match.group(1)
    store = value.upper()
    if not STORE_RE.match(store):
        raise ValueError("Must be a store id (W320) or an officeworks.com.au store link.")
    return store


def resolve_postcode(value):
    value = (value or "").strip()
    if not POSTCODE_RE.match(value):
        raise ValueError("Must be a 4-digit Australian postcode.")
    return value


def resolve_location(value):
    """Free-form store search input -> ("postcode", "3000") |
    ("coordinates", (lat, lng)) | ("suburb", "Fitzroy")."""
    value = (value or "").strip()
    if not value:
        raise ValueError("Must be a postcode, a suburb name or lat,lng coordinates.")
    if POSTCODE_RE.match(value):
        return ("postcode", value)
    match = COORDS_RE.match(value)
    if match:
        lat, lng = float(match.group(1)), float(match.group(2))
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError("Coordinates must be lat,lng (e.g. -37.81,144.96).")
        return ("coordinates", (match.group(1), match.group(2)))
    if len(value) > 80:
        raise ValueError("Location is too long.")
    return ("suburb", value)


# ---- link builders ------------------------------------------------------------

def product_link(url_keyword=None, sku=None):
    """The product page: the site's own urlKeyword when known, else the
    bare SKU (the site resolves /p/<SKU> through its search)."""
    if url_keyword:
        return SITE + PRODUCT_PATH + url_keyword
    if sku:
        return SITE + PRODUCT_PATH + sku
    return None


def category_link(seo_path):
    return SITE + CATEGORY_PATH + seo_path.strip("/") if seo_path else None


def brand_link(seo_path):
    return SITE + BRAND_PATH + seo_path if seo_path else None


def store_slug(name):
    """The store page slug the sitemap lists: the store name without its
    " Officeworks" suffix, punctuation dropped, spaces -> hyphens ("Russell
    St, Melbourne Officeworks" -> "Russell-St-Melbourne"; checked against
    all 177 sitemap entries on 2026-10-28)."""
    if not name:
        return None
    name = re.sub(r"\s+Officeworks$", "", name.strip(), flags=re.I)
    return re.sub(r"\s+", "-", re.sub(r"[^A-Za-z0-9 ]", "", name).strip()).strip("-") or None


def store_link(store_id, state=None, name=None):
    """The store page link (/storepage/W320/VIC/Russell-St-Melbourne). The
    bare /storepage/W320 is a 404 on the site, so None without state + name."""
    slug = store_slug(name)
    if not (store_id and state and slug):
        return None
    return f"{SITE}{STORE_PATH}{store_id}/{state}/{slug}"


def search_link(query, page=None):
    from urllib.parse import urlencode
    params = {"q": query}
    if page and page > 1:
        params["page"] = page
    return f"{SITE}{SEARCH_PATH}?{urlencode(params)}"


def absolute(url):
    """The site's protocol-relative image/logo URLs (//s3-ap-southeast-2...)
    -> https; already-absolute and None pass through."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url:
        return None
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return SITE + url
    return url
