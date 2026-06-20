"""
Market data service — fetches global market quotes via SerpAPI Google Finance.

API key resolution order (same pattern as ai_news.py):
  1. Environment variable SERPAPI_KEY
  2. Render secret file /etc/secrets/serpapi_key
"""
import os
import time
import httpx
from typing import Any

# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------

def _get_serpapi_key() -> str:
    # Check multiple env var names (Render dashboard may use either)
    for env_name in ("SERPAPI_KEY", "SerpAPI", "SERPAPI"):
        key = os.environ.get(env_name, "")
        if key:
            return key
    # Check multiple secret file names
    for secret_name in ("serpapi_key", "SerpAPI", "serpapi"):
        try:
            with open(f"/etc/secrets/{secret_name}") as f:
                key = f.read().strip()
            if key:
                return key
        except FileNotFoundError:
            pass
    raise RuntimeError("SERPAPI_KEY not configured.")



SERPAPI_BASE = "https://serpapi.com/search"

# ---------------------------------------------------------------------------
# Simple in-memory cache (10-minute TTL)
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, Any]] = {}
_TTL = 600  # seconds


def _cached(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < _TTL:
        return entry[1]
    return None


def _store(key: str, value: Any) -> None:
    _cache[key] = (time.time(), value)


# ---------------------------------------------------------------------------
# Low-level fetch
# ---------------------------------------------------------------------------

async def _fetch(params: dict) -> dict:
    params["api_key"] = _get_serpapi_key()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(SERPAPI_BASE, params=params)
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Helpers — parse SerpAPI responses into clean dicts
# ---------------------------------------------------------------------------

def _parse_market_item(item: dict) -> dict:
    """Normalise a single market/index/stock item from SerpAPI."""
    return {
        "ticker": item.get("stock", item.get("name", "")),
        "name": item.get("full_name", item.get("name", "")),
        "price": item.get("price"),
        "change": item.get("price_movement", {}).get("value"),
        "change_pct": item.get("price_movement", {}).get("percentage"),
        "movement": item.get("price_movement", {}).get("movement"),  # "Up" | "Down"
        "currency": item.get("currency", ""),
        "exchange": item.get("extracted_exchange", ""),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_indices() -> list[dict]:
    """Major global indices — US, Europe, Asia, LatAm."""
    cached = _cached("indices")
    if cached is not None:
        return cached

    data = await _fetch({"engine": "google_finance_markets", "trend": "indexes", "hl": "en"})
    items = []
    for section in data.get("market_trends", []):
        for item in section.get("results", []):
            items.append(_parse_market_item(item))

    _store("indices", items)
    return items


async def get_currencies() -> list[dict]:
    """Major currency pairs."""
    cached = _cached("currencies")
    if cached is not None:
        return cached

    data = await _fetch({"engine": "google_finance_markets", "trend": "currencies", "hl": "en"})
    items = []
    for section in data.get("market_trends", []):
        for item in section.get("results", []):
            items.append(_parse_market_item(item))

    _store("currencies", items)
    return items


async def get_movers(trend: str = "most-active") -> list[dict]:
    """Top movers: most-active | gainers | losers."""
    if trend not in ("most-active", "gainers", "losers"):
        trend = "most-active"

    cache_key = f"movers_{trend}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    data = await _fetch({"engine": "google_finance_markets", "trend": trend, "hl": "en"})
    items = []
    for section in data.get("market_trends", []):
        for item in section.get("results", []):
            items.append(_parse_market_item(item))

    _store(cache_key, items)
    return items


async def get_quote(ticker: str, exchange: str) -> dict | None:
    """Single ticker quote, e.g. ticker='AAPL' exchange='NASDAQ'."""
    cache_key = f"quote_{ticker}_{exchange}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    query = f"{ticker}:{exchange}"
    data = await _fetch({"engine": "google_finance", "q": query, "hl": "en"})

    summary = data.get("summary", {})
    if not summary:
        return None

    result = {
        "ticker": ticker,
        "exchange": exchange,
        "name": summary.get("title", ""),
        "price": summary.get("price"),
        "currency": summary.get("currency", ""),
        "change": summary.get("price_movement", {}).get("value"),
        "change_pct": summary.get("price_movement", {}).get("percentage"),
        "movement": summary.get("price_movement", {}).get("movement"),
        "market_cap": summary.get("market_cap"),
        "52w_high": summary.get("52_week_high"),
        "52w_low": summary.get("52_week_low"),
        "volume": summary.get("volume"),
        "pe_ratio": summary.get("pe_ratio"),
        "description": summary.get("description", ""),
    }

    _store(cache_key, result)
    return result


async def search_quote(query: str) -> dict | None:
    """Search by company name or ticker (no exchange suffix)."""
    cache_key = f"search_{query.lower()}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    data = await _fetch({"engine": "google_finance", "q": query, "hl": "en"})
    summary = data.get("summary", {})
    if not summary:
        return None

    result = {
        "ticker": data.get("summary", {}).get("stock", ""),
        "exchange": data.get("summary", {}).get("exchange", ""),
        "name": summary.get("title", ""),
        "price": summary.get("price"),
        "currency": summary.get("currency", ""),
        "change": summary.get("price_movement", {}).get("value"),
        "change_pct": summary.get("price_movement", {}).get("percentage"),
        "movement": summary.get("price_movement", {}).get("movement"),
        "market_cap": summary.get("market_cap"),
        "description": summary.get("description", ""),
    }

    _store(cache_key, result)
    return result
