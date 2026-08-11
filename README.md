# hermes-yahoo-finance

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![yfinance](https://img.shields.io/badge/powered%20by-yfinance-0066cc)](https://github.com/ranaroussi/yfinance)
[![Hermes Agent](https://img.shields.io/badge/Hermes-native%20tool-black)](https://github.com/NousResearch/hermes-agent)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Yahoo Finance](https://img.shields.io/badge/Yahoo%20Finance-33%20actions-720e9e)](https://finance.yahoo.com/)

**AI-agent-native, token-efficient access to every public Yahoo Finance website function** — 33 actions, zero API key.

> Turn `https://finance.yahoo.com/` into structured JSON from a single agent call — quotes, history, fundamentals, options, screener, sectors, and live site content (trending, charts, search, news, articles).

## Why this exists

Yahoo Finance has no official public API. `yfinance` covers the data layer, but the **website itself** has additional modules (trending tickers, raw chart bars, autocomplete search, topic news, article text) with no `yfinance` wrapper. This repo closes the gap: **33 actions covering 100% of public Yahoo Finance**.

| Tier | Backend | Auth | What it adds |
|------|---------|------|--------------|
| 1. Structured data (28) | [`yfinance`](https://github.com/ranaroussi/yfinance) via `YfData` crumb | no key | quotes, OHLCV, full info, income/balance/cash × annual/quarterly/TTM, holders, calendar, earnings, dividends, splits, options chain, recommendations, upgrades, news, search, predefined+custom screener, bulk download, sector/industry, analyst estimates, ESG, SEC filings, fund holdings, ISIN, shares, market status, lookup |
| 2. Raw website (5) | Direct Yahoo HTTP (`requests`, `query1`/`query2`) | **no crumb, no login** | `trending` (homepage module), `chart` (v8 bars + `currentTradingPeriod`), `ysearch` (scored autocomplete), `web-news` (topic sections), `web-article` (full text) |

**Not in scope:** Watchlist / Portfolio / Alerts — auth-gated (Yahoo login cookie, no public endpoint).

## Quick start

### CLI (standalone, no Hermes needed)

```bash
pip install yfinance requests
git clone https://github.com/lesterppo/hermes-yahoo-finance.git
cd hermes-yahoo-finance
python cli/yahoo_finance.py quote AAPL
python cli/yahoo_finance.py history AAPL --period 5d --metadata
python cli/yahoo_finance.py trending --count 5
python cli/yahoo_finance.py chart AAPL --period 1mo --interval 1d
python cli/yahoo_finance.py ysearch "Apple" --quotes 5 --news 1
python cli/yahoo_finance.py web-news stock-market-news --limit 5
python cli/yahoo_finance.py web-article https://finance.yahoo.com/markets/stocks/articles/...
```

33 actions total — see `yahoo_finance --help` for the full list.

### Hermes Agent (native tool)

One tool, 33 actions, gated on `import yfinance` (zero footprint until installed):

```bash
git clone https://github.com/lesterppo/hermes-yahoo-finance.git
cd hermes-yahoo-finance
./install.sh /path/to/hermes-agent   # or ~/.hermes/hermes-agent
# Then wire into a toolset (see below) and restart Hermes
```

**Wire into a toolset** — add `yahoo_finance` to `_HERMES_CORE_TOOLS` in `toolsets.py`:

```python
_HERMES_CORE_TOOLS = [
    "web_search", "web_extract", "yahoo_finance",  # ← add here
    ...
]
```

The tool is at `toolsets.py` already if you installed via `hermes-agent` with this repo's patch — otherwise apply it manually. Also appears in `hermes_cli/tools_config.py` as `CONFIGURABLE_TOOLSETS`.

**Agent usage:**

```
yahoo_finance action=quote symbol=AAPL
yahoo_finance action=history symbol=AAPL period=5d metadata=true
yahoo_finance action=trending region=US count=5
yahoo_finance action=chart symbol=AAPL period=5d interval=1d
yahoo_finance action=ysearch query="Apple" limit=5
yahoo_finance action=web-news topic=stock-market-news limit=5
yahoo_finance action=web-article url="https://finance.yahoo.com/..."
```

Schema is ~1.2KB (single `action` dispatch vs. 33 separate tools ≈ 94% token savings). Deferred behind `tool_search` — 0 tokens until disclosed.

## All 33 actions

| # | Action | Source | Notes |
|---|--------|--------|-------|
| 1 | `quote` | `get_info()` fast path | compact preset; `--fields` override; rejects `"-"` sentinel |
| 2 | `history` | `get_history()` + `get_history_metadata()` | `--metadata` adds exchange/timezone/firstTradeDate |
| 3 | `info` | `get_info()` | preview + spill to `~/.hermes/yfinance_output/` |
| 4 | `financials` | `financials`/`quarterly_*`/`ttm_*` | `--statement income\|balance\|cash --period annual\|quarterly\|ttm` |
| 5 | `holders` | `major/institutional/mutualfund/insider_*` | `--kind all\|major\|institutional\|mutualfund\|insider` |
| 6 | `calendar` | `get_calendar()` | per-symbol earnings/dividend dates |
| 7 | `earnings` | `get_earnings_dates()` | last 8 rows |
| 8 | `dividends` | `dividends` Series | capped 50 |
| 9 | `splits` | `splits` Series | |
| 10 | `options-expiries` | `Ticker.options` | |
| 11 | `options` | `option_chain(expiry)` | calls+puts |
| 12 | `recommendations` | `get_recommendations()` | history + summary |
| 13 | `upgrades` | `get_upgrades_downgrades()` | tail 30 |
| 14 | `news` | `get_news(count)` | per-symbol |
| 15 | `search` | `yf.Search` | yfinance search |
| 16 | `screener` | `yf.screen(name)` | predefined (day_gainers, most_actives, …) |
| 17 | `screener-custom` | `yf.screen(EquityQuery)` | JSON query body + crumb via YfData |
| 18 | `download` | `yf.download(group_by=ticker)` | bulk OHLCV |
| 19 | `sector` | `yf.Sector(name)` | overview + top_companies + top_etfs |
| 20 | `industry` | `yf.Industry(name)` | top_growth + performance |
| 21 | `analysis` | `get_analyst_price_targets()` + 4 DFs | bundled: price targets + EPS trend/revisions + revenue + growth |
| 22 | `esg` | `get_sustainability()` | often empty → `ok:false` |
| 23 | `filings` | `get_sec_filings()` | 10-K/Q, 8-K URLs |
| 24 | `funds` | `FundsData` (8 attrs) | ETF/mutual-fund only |
| 25 | `isin` | `get_isin()` | rejects `"-"` sentinel |
| 26 | `shares` | `get_shares_full()` | time-series + fallback to `sharesOutstanding` |
| 27 | `market` | `yf.Market(name)` | US/GB/ASIA/EUROPE… |
| 28 | `lookup` | `yf.Lookup(q)` | quoteType discovery |
| 29 | `trending` | `GET query2 /v1/finance/trending/{region}` | **beyond yfinance** — homepage module |
| 30 | `chart` | `GET query1 /v8/finance/chart/{sym}` | **beyond yfinance** — raw bars + `currentTradingPeriod` |
| 31 | `ysearch` | `GET query2 /v1/finance/search?q=` | **beyond yfinance** — scored/fuzzy |
| 32 | `web-news` | scrape `/topic/{slug}/` | **beyond yfinance** — `stock-market-news`, `crypto`, `earnings`, … |
| 33 | `web-article` | scrape article URL | **beyond yfinance** — `<title>` + `<p>` + JSON-LD fallback |

## Token efficiency

- **Tool shape:** 1 tool × 33 actions = ~1.2KB schema; 33 separate tools would be ~18KB (94% savings).
- **Output:** compact JSON (`{"ok": true, "r": {...}}`), numeric short keys, large frames spilled to `~/.hermes/yfinance_output/` with `full_file` pointer.
- **Discovery:** deferred behind `tool_search` — 0 tokens until the agent searches for it.

## Output format

```json
{"ok": true, "r": {"symbol": "AAPL", "price": 231.4, "mktCap": 3420000000000}, "symbol": "AAPL"}
{"ok": false, "error": "no ISIN for FAKE_XYZ_999", "symbol": "FAKE_XYZ_999"}
```

Large payloads (full info, multi-ticker download): `{"ok": true, "r": {"hint": "full data at ...", "full_file": "/home/.../.hermes/yfinance_output/info_AAPL_....json"}}`

## For AI agents — AGENTS.md

See **[AGENTS.md](AGENTS.md)** for agent-native integration: quick start, wire-into-toolset, 33-action dispatch examples, pitfall list, and file map. Copy-paste ready for Hermes, Claude Code, Codex.

## Skill

Full procedures, pitfalls, and audit recipes: [`skills/yahoo-finance/SKILL.md`](skills/yahoo-finance/SKILL.md)

Loaded automatically when installed via `install.sh` (`~/.hermes/skills/finance/yahoo-finance/`).

## Reliability

- `ruff check` — 0 violations
- `py_compile` — both CLI + tool clean
- Live probes — 33/33 actions verified against real Yahoo Finance on `AAPL`/`SPY`/`BTC-USD` (2026-08-12)
- Hermes: `hermes_cli` 30 tests pass; registry discovery + toolset wiring verified

## Topics

`yahoo-finance` `yfinance` `hermes-agent` `hermes-tool` `market-data` `stock-api` `yahoo-api` `ai-agent` `llm-tool` `financial-data` `stock-market` `trading` `portfolio` `screener` `earnings`

## License

MIT. Yahoo Finance data © Yahoo Inc. `yfinance` licensed separately by its authors.

