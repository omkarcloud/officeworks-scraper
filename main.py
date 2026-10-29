"""Use the scraper straight from Python — no server needed.

    python main.py

Every call is validated by the same schema the API uses and returns the same
records; results are written to output/*.json.
"""
import json
import os

from schema_fields import load_query
from officeworks import api, schemas

os.makedirs("output", exist_ok=True)


def run(schema_cls, fn, **params):
    data, error = load_query(schema_cls, {k: str(v) for k, v in params.items()})
    if error:
        raise ValueError(error)
    return fn(**data)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # a SKU or any officeworks.com.au product link
    save("product_MBAM5TS5MT.json", run(schemas.ProductSchema, api.product_details, product="MBAM5TS5MT"))

    # 24 products per page, with facets, filters and per-state availability
    save("search_macbook_air.json", run(schemas.ProductsSearchSchema, api.products_search, query="macbook air"))

    # 25 reviews per page, most helpful first
    save("reviews_SONYWHXM5B.json", run(schemas.ReviewsSchema, api.products_reviews,
                                        product="SONYWHXM5B", sort="helpful"))
