"""The `get_psx_summary` tool — a thorough Pakistan Stock Exchange snapshot.

Pulls two PSX data-portal endpoints:
- /indices      → all benchmark + sector indices (KSE-100, KSE-30, Banking, O&G…)
- /market-watch → every stock (high/low/current/change/volume)

…and returns indices + top gainers/losers (KSE-100 names) + most active stocks,
so Chippy can write a proper per-category market summary.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

INDICES_URL = "https://dps.psx.com.pk/indices"
MARKET_WATCH_URL = "https://dps.psx.com.pk/market-watch"
_UA = {"User-Agent": "Mozilla/5.0 (personal-agent/1.0)"}


def _num(s: str) -> float:
    try:
        return float(s.replace(",", "").replace("%", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def _cells(tr):
    return [" ".join(td.text_content().split()) for td in tr.xpath("./td")]


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_psx_summary() -> dict:
        """Thorough Pakistan Stock Exchange (PSX) snapshot for a market summary:
        benchmark + sector indices, top gainers, top losers, and most active stocks
        (with high/low/current/change/volume). Use for "how's the market / PSX".
        """
        import httpx
        from lxml import html as lhtml

        # --- indices (benchmark + sector) ---
        idoc = lhtml.fromstring(
            httpx.get(INDICES_URL, headers=_UA, timeout=25, follow_redirects=True).text
        )
        indices = []
        for tr in idoc.xpath("//table//tbody//tr"):
            c = _cells(tr)
            if len(c) >= 6:
                indices.append(
                    {"index": c[0], "current": c[3], "change": c[4], "percent_change": c[5]}
                )

        # --- per-stock market watch ---
        mdoc = lhtml.fromstring(
            httpx.get(MARKET_WATCH_URL, headers=_UA, timeout=30, follow_redirects=True).text
        )
        stocks = []
        for tr in mdoc.xpath("//table//tbody//tr"):
            c = _cells(tr)
            if len(c) < 11:
                continue
            stocks.append(
                {
                    "symbol": c[0],
                    "indices": c[2],
                    "high": c[5],
                    "low": c[6],
                    "current": c[7],
                    "change": c[8],
                    "change_pct": c[9],
                    "volume": c[10],
                    "_pct": _num(c[9]),
                    "_vol": _num(c[10]),
                }
            )

        def clean(rows):
            return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]

        kse100 = [s for s in stocks if "KSE100" in s["indices"]]
        gainers = sorted(kse100, key=lambda s: s["_pct"], reverse=True)[:5]
        losers = sorted(kse100, key=lambda s: s["_pct"])[:5]
        most_active = sorted(stocks, key=lambda s: s["_vol"], reverse=True)[:5]

        if not indices and not stocks:
            return {"error": "Could not read PSX data right now."}

        return {
            "source": "Pakistan Stock Exchange (dps.psx.com.pk)",
            "indices": indices,
            "top_gainers": clean(gainers),
            "top_losers": clean(losers),
            "most_active": clean(most_active),
        }
