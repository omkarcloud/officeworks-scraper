"""Configuration for the Officeworks Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT               port the API listens on (default 8000)
    CACHE              0 turns the in-memory response cache off (default on)
    OFFICEWORKS_PROXY  proxy URL for every request to officeworks.com.au, e.g.
                       http://user:pass@host:port (default: none — direct).
                       Search, suggestions, listings, reviews and questions
                       come from the site's search and review services, which
                       answer any connection and never use this proxy.
                       Officeworks' own JSON (product details, prices, stock,
                       categories, brands, stores, sitemaps) sits behind AWS
                       WAF, which answers most servers but shows some IPs a
                       "Human Verification" page; if those endpoints answer
                       500 "blocked", set an Australian proxy.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# In-memory response cache (cache.py); per-endpoint TTLs live in
# officeworks/cache_config.py.
CACHE_ENABLED = os.environ.get("CACHE", "1").lower() not in ("0", "false", "no", "off")

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

OFFICEWORKS_PROXY = os.environ.get("OFFICEWORKS_PROXY") or None


def officeworks_proxy():
    """The proxy for one curl session (None = direct)."""
    return os.environ.get("OFFICEWORKS_PROXY") or None
