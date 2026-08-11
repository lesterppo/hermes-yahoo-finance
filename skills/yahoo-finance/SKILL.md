---
name: yahoo-finance
description: Use when accessing Yahoo Finance data or website functions.
version: 1.1.0
author: Peter (lesterppo)
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [yahoo-finance, yfinance, market-data, hermes-tool]
    category: finance
    related_skills: [hermes-tool-development, google-finance, fin-agent-cli]
---

# Yahoo Finance — Full Website Coverage CLI + Hermes Tool

AI-agent-native, token-efficient access to **every public Yahoo Finance website function** — 33 actions, zero API key. Two tiers: 28 via `yfinance` + 5 raw Yahoo HTTP beyond yfinance.

## When to Use

- Any request involving `finance.yahoo.com`: quotes, charts, fundamentals, holders, options, screener, sectors/industries, or content (news, trending, articles)
- User asks `@url:https://finance.yahoo.com/` to operate or automate
- Need bulk market data without paid APIs

## Two-Tier Architecture

| Tier | Backend | Auth | Actions |
|------|---------|------|---------|
| 1. Structured data | `yfinance` (Python) | no key, crumb via YfData | 28: `quote`, `history` (+ `--metadata`), `info`, `financials`, `holders`, `calendar`, `earnings`, `dividends`, `splits`, `options`/`options-expiries`, `recommendations`, `upgrades`, `news`, `search`, `screener`/`screener-custom`, `download`, `sector`/`industry`, `analysis`, `esg`, `filings`, `funds`, `isin`, `shares`, `market`, `lookup` |
| 2. Raw website (beyond yfinance) | Direct Yahoo HTTP (`requests`) | **no crumb, no login** | 5: `trending` (query2 trending), `chart` (v8 chart), `ysearch` (autocomplete), `web-news` (topic scrape), `web-article` (article extract) |

> **Not applicable:** Watchlist / Portfolio / Alerts — auth-gated (Yahoo login cookie), no public endpoint. Explain, don't pretend.

## CLI Entry Point

```
yahoo_finance <action> [args] [--flags]
# Examples:
yahoo_finance quote AAPL
yahoo_finance history AAPL --period 5d --metadata
yahoo_finance analysis AAPL
yahoo_finance funds SPY
yahoo_finance trending --count 5
yahoo_finance chart AAPL --period 5d --interval 1d
yahoo_finance ysearch "Apple" --quotes 5 --news 1
yahoo_finance web-news stock-market-news --limit 5
yahoo_finance web-article https://finance.yahoo.com/markets/stocks/articles/...
```

- Output: compact JSON (`{"ok": true, "r": {...}}` or `{"ok": false, "error": ...}`); large frames spilled to `~/.hermes/yfinance_output/*.json` with `full_file` + `hint`.
- File: `~/.hermes/scripts/yahoo-finance/yahoo_finance.py` (also `~/.local/bin/yahoo_finance`)
- Token cost: `quote` ~934 chars / ~183 tokens (38 fields); `info` spills full 200+ keys to file, preview 14 keys inline.

## Hermes Tool Dispatch

- Tool: `yahoo_finance`, toolset: `yahoo_finance` (registered in `toolsets.py` + `hermes_cli/tools_config.py`, on by default)
- Single `action` dispatch; schema mirrors CLI flags (`symbol`, `query`, `screener`, `sector`, `industry`, `market`, `period`, `interval`, `statement`, `kind`, `expiry`, `symbols`, `fields`, `limit`, `offset`, `section`, `start`/`end`, `metadata` (bool), `region`, `count`, `url`, `topic`, `symbols_only`).
- Implementation: `tools/yahoo_finance_tool.py` → `_build_argv()` → `subprocess.run([sys.executable, CLI, sub, ...], timeout=45)` → passthrough JSON. Gated on `import yfinance`.
- Aliases: `web-news`/`web_news`, `web-article`/`web_article`.

## Supported Actions (33)

| action | yfinance / Yahoo source | notes |
|--------|------------------------|-------|
| `quote` | `Ticker.get_info()` fast path + `key_map` | rejects invalid ticker (`"-"` sentinel) |
| `history` | `Ticker.history()` + `get_history_metadata()` | `--metadata` adds exchange/timezone/firstTradeDate |
| `info` | `get_info()` | preview+spill; section filter |
| `financials` | `financials`/`quarterly_*`/`ttm_*` | aliases `incomestmt/balancesheet/cashflow` covered |
| `holders` | `major/institutional/mutualfund/insider_*` | bundles rosters |
| `calendar` | `get_calendar()` | per-symbol earnings/dividend dates |
| `earnings` | `get_earnings_dates()` | DF tail |
| `dividends` | `dividends` Series | 50-row inline cap |
| `splits` | `splits` Series | |
| `options-expiries` | `Ticker.options` | |
| `options` | `option_chain(expiry)` | calls+puts truncated |
| `recommendations` | `get_recommendations()` + summary | history+summary |
| `upgrades` | `get_upgrades_downgrades()` | tail 30 |
| `news` | `get_news(count)` | per-symbol news |
| `search` | `yf.Search` | quotes+news_preview |
| `screener` | `yf.screen(name)` / `PREDEFINED_SCREENER_QUERIES` | predefined list |
| `screener-custom` | `yf.screen(EquityQuery)` via `_dict_to_query` | crumb via YfData |
| `download` | `yf.download(..., group_by="ticker")` | MultiIndex handling |
| `sector` | `yf.Sector(name)` | `overview + top_companies + top_etfs` |
| `industry` | `yf.Industry(name)` | also `top_growth/performance` |
| `analysis` | `get_analyst_price_targets()` + `eps_trend/eps_revisions/revenue_estimate/growth_estimates` | bundled |
| `esg` | `get_sustainability()` | currently empty on most tickers → `ok:false` |
| `filings` | `get_sec_filings()` | 10-K/Q, 8-K URLs |
| `funds` | `Ticker.funds_data` (FundsData: 8 attrs) | ETF/mutual-fund only; equity → `ok:false` |
| `isin` | `get_isin()` | rejects `"-"` sentinel |
| `shares` | `get_shares_full()` + `sharesOutstanding` fallback | time-series |
| `market` | `yf.Market(name)` | valid: US/GB/ASIA/EUROPE/... |
| `lookup` | `yf.Lookup(q)` | quoteType discovery |
| `trending` | `GET query2 /v1/finance/trending/{region}` | **beyond yfinance**, no auth — site homepage module |
| `chart` | `GET query1 /v8/finance/chart/{sym}` | **beyond yfinance**, raw `meta`+`currentTradingPeriod` |
| `ysearch` | `GET query2 /v1/finance/search?q=` | **beyond yfinance**, scored/fuzzy, `score/sector/industry` |
| `web-news` | `HTML scrape /topic/{slug}/` | **beyond yfinance**, keyless; valid: `stock-market-news`, `latest-news`, `earnings`, `economy`, `personal-finance`, `crypto` |
| `web-article` | `HTML scrape article URL` | **beyond yfinance**, `<title>`+`<p>`+JSON-LD `articleBody` fallback |
| *(auth-only)* | Watchlist/Portfolio/Alerts | cookie-gated, no public endpoint |

## Full-Coverage Audit Recipe

1. Enumerate `dir(yf.Ticker("AAPL"))` minus `_` prefixes; normalize aliases (`incomestmt→income`, `balancesheet→balance`, `cashflow→cash`).
2. Map each distinct surface to a CLI action; gaps are those with no mapping (analysis/ESG/filings/funds/ISIN/shares/industry/market/lookup + history_metadata).
3. Probe every gap live **before** coding (see `references/full-coverage-gaps-2026-08-12.md`). Expected live: `sustainability` empty, `funds_data` fails on equities, `get_shares()` raises `NotImplemented` (use `get_shares_full`), `Market GB/ASIA` returns `None`, `Lookup.get_*()` takes no `query` arg.
4. Implement bundled vs single actions: `analysis` bundles 5 estimate surfaces to keep schema under 200 tokens; others are 1:1.
5. Add `history --metadata` as a flag (not a new action) — embeds `get_history_metadata()` under `meta.history_metadata`.
6. For beyond-yfinance, verify every raw endpoint with `requests` before coding — they require **no crumb** (see `references/beyond-yfinance.md`).

## Pitfalls

- **FundsData is not nullable on equities**: `Ticker("AAPL").funds_data` returns `FundsData` even for non-funds; every sub-attribute raises `No Fund data found`. Probe `sector_weightings`/`fund_overview` before declaring coverage.
- **ISIN sentinel `"-"`**: invalid tickers return `"-"` not `None`. Check `isin.strip() == "-"` or fake tickers appear `ok:true` with `isin:"-"`.
- **`get_shares()` is unimplemented**: raises `Have not implemented fetching 'shares'`. Use `get_shares_full(start=...)` + fallback to `info["sharesOutstanding"]`.
- **`get_sustainability()` is effectively empty**: AAPL/MSFT/TSLA all return empty DF (2026-08-12). Surface as `ok:false`.
- **`Market` valid set is small**: only `US` reliably returns `status`; `GB/ASIA/CURRENCIES/CRYPTOCURRENCIES` return `None`.
- **`Lookup` API shape**: `yf.Lookup("AI")` → `.all` (DF) and `.get_stock()` / `.get_etf()` with **no args** (not `query=`).
- **`history_metadata` is dict**: `get_history_metadata()` returns dict with `currency/symbol/exchangeName/.../firstTradeDate`.
- **Screener crumb**: use `yfinance.screen()` via `YfData` path; raw `requests` to `query1` 401s.
- **Patch overlap**: extending `yahoo_finance.py` with a heredoc that duplicates the tail of `do_sector` creates an indented orphan → `IndentationError`. Dedup stale tail before inserting new `def`s.
- **Schema line wrap**: `YAHOO_FINANCE_SCHEMA` description is an implicit string concatenation — breaking a line without closing `"` gives `unterminated string literal`.
- **web-news topics**: `technology` slot 404s; valid topics are `stock-market-news`, `latest-news`, `earnings`, `economy`, `personal-finance`, `crypto` — include hint in 404 error.
- **chart vs history**: use `chart` (v8) for raw bars/meta; `history` for adjusted OHLCV + computed returns.
- **Beyond-yfinance wiring**: the 5 raw actions use `_yahoo_get()` helper (`requests` + UA header) — no `yfinance` import needed, no crumb.

## Wiring Checklist (Hermes Tool)

- `tools/yahoo_finance_tool.py`: `YAHOO_FINANCE_SCHEMA` (35 action enum incl. `trending/chart/ysearch/web-news/web-article`), `_ACTION_MAP` (35 incl. `web_news`/`web_article` aliases), `_NEEDS_SYMBOL` (17 symbol-bound + beyond-yfinance branches), `registry.register(toolset="yahoo_finance", check_fn=_check_yfinance)`.
- `toolsets.py`: `"yahoo_finance": {"description": "...", "tools": ["yahoo_finance"], "includes": []}` (deferred; discovery populates `get_available_toolsets`).
- `hermes_cli/tools_config.py`: optional `CONFIGURABLE_TOOLSETS` entry for UI visibility.
- Verify: `rm tool_discovery_cache.json; discover_builtin_tools(); "yahoo_finance" in registry.get_available_toolsets()` + handler smoke `quote AAPL` → `ok:true`.

## Verification

```bash
yahoo_finance --help                              # 33 subparsers
yahoo_finance quote AAPL
yahoo_finance history AAPL --period 5d --metadata  # meta.history_metadata present
yahoo_finance analysis AAPL
yahoo_finance trending --count 5                  # beyond yfinance
yahoo_finance chart AAPL --period 5d              # beyond yfinance
yahoo_finance ysearch "Apple" --quotes 3          # beyond yfinance
yahoo_finance web-news stock-market-news --limit 3
yahoo_finance web-article https://finance.yahoo.com/markets/stocks/articles/...
python3 -m py_compile ~/.hermes/scripts/yahoo-finance/yahoo_finance.py
.venv/bin/python -m ruff check tools/yahoo_finance_tool.py ~/.hermes/scripts/yahoo-finance/yahoo_finance.py
```

## References

- `references/full-coverage-gaps-2026-08-12.md` — live probe of the 11 gap surfaces + Sector/Industry/Market/Lookup detail
- `references/beyond-yfinance.md` — raw Yahoo HTTP endpoints beyond yfinance (trending/chart/ysearch/web-news/web-article), curl probes, HTML scrape traps
- `references/sentinel-handling.md` — ISIN `"-"` and funds equity-vs-ETF probe patterns
- `references/audit-recipe.md` — `dir(Ticker)` → alias normalization → gap table
- `references/verification.md` — 33-action deep-test matrix (CLI + Hermes tool + live API)
- `references/coverage-map.md` — website sections → yfinance attrs → CLI actions mapping
