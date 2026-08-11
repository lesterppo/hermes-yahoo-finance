#!/usr/bin/env python3
"""
Yahoo Finance native Hermes tool — thin wrapper over yahoo_finance CLI.

Single tool `yahoo_finance` with action dispatch. Token-efficient: short keys,
compact numeric fields, file spill for large frames.

Actions:
  quote, history, info, financials, holders, calendar, earnings,
  dividends, splits, options_expiries, options, recommendations,
  upgrades, news, search, screener, screener_custom, download, sector

Gated on `yfinance` import (check_fn). Zero API keys — Yahoo public data.
"""
from __future__ import annotations
import json
import subprocess
import sys
import os
import shlex
from pathlib import Path

CLI = Path.home() / ".hermes" / "scripts" / "yahoo-finance" / "yahoo_finance.py"
# Also support direct module run if symlink/workdir differs
CLI_FALLBACK = Path(__file__).parent.parent / ".hermes" / "scripts" / "yahoo-finance" / "yahoo_finance.py"

# ── check_fn ──
def _check_yfinance() -> bool:
    try:
        import yfinance  # noqa: F401
        return True
    except ImportError:
        return False

# ── schema ──
YAHOO_FINANCE_SCHEMA = {
    "name": "yahoo_finance",
    "description": (
        "Yahoo Finance — quotes, history, fundamentals, holders, options, screener, search, bulk download, analysis/estimates, ESG, filings, funds, ISIN, shares, sector/industry, market, lookup, plus LIVE Yahoo website: trending, chart (v8), ysearch (autocomplete), web-news, web-article. "
        "No API key. Use action dispatch. Examples: "
        "quote AAPL | history AAPL period=1mo metadata=true | trending region=US | "
        "chart AAPL period=5d | ysearch Apple | web-news topic=stock-market-news | "
        "search 'Apple' | screener day_gainers | options AAPL | financials AAPL statement=income"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": (
                    "Action: quote | history | info | financials | holders | calendar | earnings | "
                    "dividends | splits | options_expiries | options | recommendations | upgrades | "
                    "news | search | screener | screener_custom | download | sector | industry | "
                    "analysis | esg | filings | funds | isin | shares | market | lookup | "
                    "trending | chart | ysearch | web-news | web-article"
                ),
            },
            "symbol": {"type": "string", "description": "Ticker symbol (AAPL, 0700.HK, BTC-USD). Required for symbol-bound actions."},
            "query": {"type": "string", "description": "Search query (for search) or JSON string (for screener_custom)."},
            "screener": {"type": "string", "description": "Predefined screener name (day_gainers, most_actives, etc.)"},
            "sector": {"type": "string", "description": "Sector name (technology, healthcare, ...)"},
            "period": {"type": "string", "description": "history: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max | financials: annual,quarterly,ttm"},
            "interval": {"type": "string", "description": "history/download interval: 1m,5m,15m,30m,1h,1d,1wk,1mo ..."},
            "statement": {"type": "string", "description": "financials: income | balance | cash"},
            "kind": {"type": "string", "description": "holders: all|major|institutional|mutualfund|insider — options: calls|puts|both"},
            "expiry": {"type": "string", "description": "Option expiry YYYY-MM-DD (default nearest)"},
            "symbols": {"type": "string", "description": "Comma-separated symbols for download (overrides symbol)"},
            "fields": {"type": "string", "description": "Comma-separated info keys for quote"},
            "limit": {"type": "integer", "description": "Row limit / screener count / news count"},
            "offset": {"type": "integer", "description": "Screener offset"},
            "section": {"type": "string", "description": "info: comma-separated quote,profile,stats"},
            "industry": {"type": "string", "description": "Industry name (software-infrastructure, semiconductors, ...)"},
            "market": {"type": "string", "description": "Market name: US, EUROPE, ASIA, ... (for market status)"},
            "start": {"type": "string", "description": "Start date YYYY-MM-DD (for shares)"},
            "end": {"type": "string", "description": "End date YYYY-MM-DD (for shares)"},
            "metadata": {"type": "boolean", "description": "history: include history_metadata when true"},
            "region": {"type": "string", "description": "trending: region US, CA, GB, ..."},
            "count": {"type": "integer", "description": "trending/web-news count; ysearch news/quotes count alias"},
            "url": {"type": "string", "description": "web-article: Yahoo Finance article URL"},
            "topic": {"type": "string", "description": "web-news: topic slug (stock-market-news, earnings, ai, ...)"},
            "newsCount": {"type": "integer", "description": "ysearch: news result count override"},
            "quotesCount": {"type": "integer", "description": "ysearch: quotes result count override"},
            "symbols_only": {"type": "boolean", "description": "trending: symbols-only when true"},
        },
        "required": ["action"],
    },
}

# Map action → CLI subcommand + arg translation
_ACTION_MAP = {
    "quote": "quote",
    "history": "history",
    "info": "info",
    "financials": "financials",
    "holders": "holders",
    "calendar": "calendar",
    "earnings": "earnings",
    "dividends": "dividends",
    "splits": "splits",
    "options_expiries": "options-expiries",
    "options": "options",
    "recommendations": "recommendations",
    "upgrades": "upgrades",
    "news": "news",
    "search": "search",
    "screener": "screener",
    "screener_custom": "screener-custom",
    "download": "download",
    "sector": "sector",
    "industry": "industry",
    "analysis": "analysis",
    "esg": "esg",
    "filings": "filings",
    "funds": "funds",
    "isin": "isin",
    "shares": "shares",
    "market": "market",
    "lookup": "lookup",
    "trending": "trending",
    "chart": "chart",
    "ysearch": "ysearch",
    "web-news": "web-news",
    "web_news": "web-news",
    "web-article": "web-article",
    "web_article": "web-article",
}

_NEEDS_SYMBOL = {"quote","history","info","financials","holders","calendar","earnings","dividends","splits","options_expiries","options","recommendations","upgrades","news","analysis","esg","filings","funds","isin","shares"}

def _resolve_cli() -> Path:
    if CLI.exists():
        return CLI
    if CLI_FALLBACK.exists():
        return CLI_FALLBACK
    # try PATH
    import shutil
    p = shutil.which("yahoo_finance")
    if p:
        return Path(p)
    return CLI

def _build_argv(args: dict) -> list[str]:
    action = (args.get("action") or "").strip().lower()
    if action not in _ACTION_MAP:
        raise ValueError(f"unknown action '{action}'; valid: {sorted(_ACTION_MAP)}")
    sub = _ACTION_MAP[action]
    cli = str(_resolve_cli())
    argv = [sys.executable, cli, sub]

    symbol = (args.get("symbol") or "").strip()
    query = (args.get("query") or "").strip()
    screener = (args.get("screener") or "").strip()
    sector = (args.get("sector") or "").strip()
    symbols = (args.get("symbols") or "").strip()

    # positional handling per subcommand
    if action in _NEEDS_SYMBOL:
        if not symbol:
            raise ValueError(f"action '{action}' requires symbol")
        argv.append(symbol)
    elif action == "search":
        q = query or symbol
        if not q:
            raise ValueError("search requires query (or symbol as query)")
        argv.append(q)
    elif action == "screener":
        name = screener or query or symbol
        if not name:
            raise ValueError("screener requires screener name (screener= or query=)")
        argv.append(name)
    elif action == "screener_custom":
        pass  # no positional
    elif action == "download":
        syms = symbols or symbol
        if not syms:
            raise ValueError("download requires symbols (comma-separated) or symbol")
        argv.append(syms)
    elif action == "sector":
        name = sector or symbol or query
        if not name:
            raise ValueError("sector requires sector name")
        argv.append(name)
    elif action == "industry":
        name = (args.get("industry") or sector or symbol or query or "").strip()
        if not name:
            raise ValueError("industry requires industry name (e.g. software-infrastructure)")
        argv.append(name)
    elif action == "trending":
        pass  # all flags
    elif action == "chart":
        if not symbol:
            raise ValueError("chart requires symbol")
        argv.append(symbol)
    elif action == "ysearch":
        q2 = query or symbol
        if not q2:
            raise ValueError("ysearch requires query")
        argv.append(q2)
    elif action in ("web-news", "web_news"):
        tp = (args.get("topic") or query or symbol or "").strip()
        if not tp:
            raise ValueError("web-news requires topic (e.g. stock-market-news)")
        argv.append(tp)
    elif action in ("web-article", "web_article"):
        u = (args.get("url") or query or symbol or "").strip()
        if not u:
            raise ValueError("web-article requires url")
        argv.append(u)
    elif action in ("analysis","esg","filings","funds","isin","shares"):
        if not symbol:
            raise ValueError(f"action '{action}' requires symbol")
        argv.append(symbol)
    elif action == "market":
        name = (args.get("market") or sector or symbol or query or "US").strip()
        argv.append(name)
    elif action == "lookup":
        q = query or symbol
        if not q:
            raise ValueError("lookup requires query (or symbol as query)")
        argv.append(q)

    # optional flags
    def _flag(name, val):
        if val is not None and str(val).strip() != "":
            argv.extend([f"--{name}", str(val).strip()])

    if action == "quote":
        if args.get("fields"):
            _flag("fields", args["fields"])
    elif action == "history":
        _flag("period", args.get("period"))
        _flag("interval", args.get("interval"))
        if args.get("limit") is not None:
            _flag("limit", args["limit"])
        if args.get("metadata"):
            argv.append("--metadata")
    elif action == "info":
        if args.get("section"):
            _flag("section", args["section"])
    elif action == "financials":
        _flag("statement", args.get("statement"))
        _flag("period", args.get("period"))
    elif action == "holders":
        _flag("kind", args.get("kind"))
    elif action == "earnings":
        if args.get("limit") is not None:
            _flag("limit", args["limit"])
    elif action in ("dividends",):
        if args.get("period"):
            _flag("period", args["period"])
    elif action == "options":
        if args.get("expiry"):
            _flag("expiry", args["expiry"])
        if args.get("kind"):
            _flag("kind", args["kind"])
        if args.get("limit") is not None:
            _flag("limit", args["limit"])
    elif action == "news":
        if args.get("limit") is not None:
            _flag("count", args["limit"])
            argv  # --count is the CLI flag name
        # CLI uses --count for news; map limit→count (already handled)
    elif action == "search":
        if args.get("limit") is not None and action == "search":
            _flag("limit", args["limit"])
    elif action == "screener":
        if args.get("limit") is not None:
            _flag("limit", args["limit"])
        if args.get("offset") is not None:
            _flag("offset", args["offset"])
    elif action == "screener_custom":
        if not query:
            raise ValueError("screener_custom requires query (JSON string)")
        _flag("query", query)
        if args.get("limit") is not None:
            _flag("limit", args["limit"])
        if args.get("offset") is not None:
            _flag("offset", args["offset"])
    elif action == "download":
        _flag("period", args.get("period"))
        _flag("interval", args.get("interval"))
    elif action == "sector":
        pass
    elif action == "trending":
        if args.get("region"):
            _flag("region", args["region"])
        if args.get("count") is not None:
            _flag("count", args["count"])
        if args.get("symbols_only"):
            argv.append("--symbols-only")
    elif action == "chart":
        _flag("period", args.get("period"))
        _flag("interval", args.get("interval"))
    elif action == "ysearch":
        if args.get("quotesCount") is not None:
            _flag("quotes", args["quotesCount"])
        elif args.get("limit") is not None:
            _flag("quotes", args["limit"])
        if args.get("newsCount") is not None:
            _flag("news", args["newsCount"])
        elif args.get("count") is not None:
            _flag("news", args["count"])
    elif action == "web-news":
        if args.get("limit") is not None:
            _flag("limit", args["limit"])
    elif action in ("web-news_alias",):  # no-op guard
        pass
    elif action in ("web-article","web_article"):
        pass
    elif action == "industry":
        pass
    elif action in ("analysis","esg","funds","isin"):
        pass
    elif action == "filings":
        if args.get("limit") is not None:
            _flag("limit", args["limit"])
    elif action == "shares":
        if args.get("start"):
            _flag("start", args["start"])
        if args.get("end"):
            _flag("end", args["end"])
        if args.get("limit") is not None:
            _flag("limit", args["limit"])
    elif action == "market":
        pass
    elif action == "lookup":
        if args.get("kind"):
            _flag("kind", args["kind"])
        if args.get("limit") is not None:
            _flag("limit", args["limit"])
    elif action == "history":
        # extra: metadata flag lives inside history branch; handle bool
        if args.get("metadata"):
            argv.append("--metadata")

    # Fix: news used --count not --limit
    # Already handled above — for screener search the _flag adds correctly.
    # Patch news: if we added --count via limit, it's correct. Ensure no stray --limit left.
    return argv

def _handle_yahoo_finance(args: dict, **kw) -> str:
    # validate
    action = (args.get("action") or "").strip()
    if not action:
        from tools.registry import tool_error
        return tool_error("action is required")
    try:
        argv = _build_argv(args)
    except ValueError as e:
        from tools.registry import tool_error
        return tool_error(str(e))

    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired:
        from tools.registry import tool_error
        return tool_error("yahoo_finance timed out (45s)")
    except Exception as e:
        from tools.registry import tool_error
        return tool_error(f"yahoo_finance exec failed: {e}")

    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()

    # CLI emits JSON to stdout; pass through verbatim (already compact)
    if out:
        # Validate it's JSON; if not, wrap
        try:
            json.loads(out)
            return out
        except Exception:
            # non-JSON output → wrap
            from tools.registry import tool_error
            return tool_error(f"unexpected output: {out[:800]} stderr:{err[:400]}")
    # no stdout → error
    from tools.registry import tool_error
    if err:
        return tool_error(err[:2000])
    return tool_error(f"yahoo_finance returned empty output (exit {result.returncode}) stderr:{err[:800]}")

# ── registry ──
from tools.registry import registry
registry.register(
        name="yahoo_finance",
        toolset="yahoo_finance",
        schema=YAHOO_FINANCE_SCHEMA,
        handler=_handle_yahoo_finance,
        check_fn=_check_yfinance,
        emoji="📈",
        max_result_size_chars=120_000,
    )
