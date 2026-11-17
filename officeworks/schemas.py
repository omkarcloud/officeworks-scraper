"""Request schemas for /officeworks/* (marshmallow, one per route).

ONE param per input (tripadvisor QueryOrIdField convention): `product`
takes a SKU or a product link, `category` a path or a category link,
`brand` a name / slug / brand link, `store` an id or a store link. Unknown
query params are rejected by BaseSchema.
"""
import os
import sys

from marshmallow import ValidationError, fields, validate, validates_schema

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schema_fields import (BaseSchema, ChoiceField, CommaListField, Flag, LimitField, PageField,  # noqa: E402
                           Price, Quantity, QueryField, RefField, StrippedString)
from officeworks import refs  # noqa: E402
from scraper_utils.schema import max_length as _max_length

# Algolia caps every query at 1,000 hits (paginationLimitedTo); 24 per page
# is what the site's own listing pages use.
LISTING_PAGE_SIZE = 24
LISTING_MAX_PAGE = 42            # ceil(1000 / 24)
REVIEWS_PAGE_SIZE = 25
QUESTIONS_PAGE_SIZE = 20
SITEMAP_PAGE_SIZE = 1000
BULK_MAX_PRODUCTS = 20
PRICES_MAX_PRODUCTS = 50

SORT_CHOICES = {
    "relevance": "bestmatch-personal",
    "newest": "newest",
    "price_low": "price-asc",
    "price_high": "price-desc",
    "rating_high": "rating-desc",
    "rating_low": "rating-asc",
    "name": "name",
}

REVIEW_SORT_CHOICES = {
    "newest": "SubmissionTime:desc",
    "oldest": "SubmissionTime:asc",
    "highest": "Rating:desc",
    "lowest": "Rating:asc",
    "helpful": "TotalPositiveFeedbackCount:desc",
}

# ChoiceField lower-cases list choices; the site's facet values are upper-case.
STATE_CHOICES = {s: s for s in refs.AU_STATES}


# The site's landing collections that are plain category paths in Algolia.
SPECIALS_CHOICES = {
    "deals": "deals",
    "clearance": "clearance",
}


class ProductRefField(RefField):
    resolver = staticmethod(refs.resolve_product)


class CategoryRefField(RefField):
    resolver = staticmethod(refs.resolve_category)


class BrandRefField(RefField):
    resolver = staticmethod(refs.resolve_brand)


class StoreRefField(RefField):
    resolver = staticmethod(refs.resolve_store)


class ProductListField(CommaListField):
    """'lom280blk, https://www.officeworks.com.au/shop/officeworks/p/...'
    -> ['LOM280BLK', ...] through the product resolver."""

    def __init__(self, max_items=BULK_MAX_PRODUCTS, **kwargs):
        # CommaListField defaults load_default=None, which marshmallow refuses
        # on a required field: build it optional, then mark it required.
        super().__init__(upper=False, max_items=max_items, **kwargs)
        self.required = True
        self.load_default = fields.missing_

    def _deserialize(self, value, attr, data, **kwargs):
        items = super()._deserialize(value, attr, data, **kwargs)
        if not items:
            raise ValidationError("Give at least one SKU or product link.")
        out = []
        for item in items:
            try:
                sku = refs.resolve_product(item)
            except ValueError as e:
                raise ValidationError(f"{item!r}: {e}")
            if sku not in out:
                out.append(sku)
        return out


class PostcodeField(StrippedString):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        try:
            return refs.resolve_postcode(value)
        except ValueError as e:
            raise ValidationError(str(e))


class _ListingFilters(BaseSchema):
    """Filters + sort + page shared by every Algolia listing route."""
    page = PageField(max_page=LISTING_MAX_PAGE)
    sort = ChoiceField(SORT_CHOICES, load_default="bestmatch-personal")
    brand = BrandRefField(required=False, load_default=None)
    min_price = Price()
    max_price = Price()
    min_rating = fields.Integer(load_default=None, strict=False, validate=validate.Range(min=1, max=5))
    state = ChoiceField(STATE_CHOICES)
    clearance = Flag()
    in_stock_online = Flag()

    @validates_schema
    def _price_bounds(self, data, **kwargs):
        lo, hi = data.get("min_price"), data.get("max_price")
        if lo is not None and hi is not None and lo > hi:
            raise ValidationError("min_price must not exceed max_price.", "min_price")


class ProductsSearchSchema(_ListingFilters):
    query = QueryField()
    category = CategoryRefField(required=False, load_default=None)


class SuggestionsSchema(BaseSchema):
    query = QueryField(max_length=100)
    limit = LimitField(default=10, max_size=20)


class ProductSchema(BaseSchema):
    product = ProductRefField()


class ProductsBulkSchema(BaseSchema):
    products = ProductListField(max_items=BULK_MAX_PRODUCTS)


class ProductsPricesSchema(BaseSchema):
    products = ProductListField(max_items=PRICES_MAX_PRODUCTS)


class AvailabilitySchema(BaseSchema):
    product = ProductRefField()
    store = StoreRefField()
    postcode = PostcodeField()
    quantity = Quantity(load_default=1, max_value=999)


class ReviewsSchema(BaseSchema):
    product = ProductRefField()
    page = PageField(max_page=400)
    sort = ChoiceField(REVIEW_SORT_CHOICES, load_default="SubmissionTime:desc")


class QuestionsSchema(BaseSchema):
    product = ProductRefField()
    page = PageField(max_page=200)


class EmptySchema(BaseSchema):
    """Routes with no parameters (categories, brands)."""


class CategorySchema(BaseSchema):
    category = CategoryRefField()


class CategoryProductsSchema(_ListingFilters):
    category = CategoryRefField()
    query = QueryField(required=False, load_default=None, validate=_max_length(200))


class BrandProductsSchema(_ListingFilters):
    brand = BrandRefField()
    category = CategoryRefField(required=False, load_default=None)
    query = QueryField(required=False, load_default=None, validate=_max_length(200))


class SpecialsSchema(_ListingFilters):
    collection = ChoiceField(SPECIALS_CHOICES, load_default="deals")
    category = CategoryRefField(required=False, load_default=None)
    query = QueryField(required=False, load_default=None, validate=_max_length(200))


class StoresSchema(BaseSchema):
    state = ChoiceField(STATE_CHOICES)


class StoresSearchSchema(BaseSchema):
    location = StrippedString(required=True, validate=validate.Length(min=1, max=80))
    limit = LimitField(default=10, max_size=50)

    @validates_schema
    def _resolve(self, data, **kwargs):
        try:
            refs.resolve_location(data.get("location"))
        except ValueError as e:
            raise ValidationError(str(e), "location")


class StoreSchema(BaseSchema):
    store = StoreRefField()


class LocationsSuggestionsSchema(BaseSchema):
    query = QueryField(max_length=80)


class SitemapProductsSchema(BaseSchema):
    page = PageField(max_page=200)


class SitemapLinksSchema(BaseSchema):
    type = ChoiceField(list(refs.SITEMAP_TYPES), load_default=None)
    page = PageField(max_page=200)
