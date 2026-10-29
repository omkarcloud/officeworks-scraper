"""The one network helper the officeworks module needs: the Accept-Language a
session sends. The scraper connects directly (or through OFFICEWORKS_PROXY),
so every session announces the language list Chrome sends by default."""

ACCEPT_LANGUAGE = "en-US,en;q=0.9"


def site_accept_language(site=None):
    return ACCEPT_LANGUAGE


def accept_language(proxy=None, country=None):
    return ACCEPT_LANGUAGE
