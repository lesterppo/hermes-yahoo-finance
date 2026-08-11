# AGENTS.md — AI agent instructions for hermes-yahoo-finance

This document tells AI coding agents (Hermes, Claude Code, Codex, etc.) everything they need to install, configure, and use the `yahoo_finance` tool.

## What this repo provides

A Hermes Agent **native tool** + standalone CLI that wraps [Yahoo Finance](https://finance.yahoo.com/) — 33 actions, zero API key, 100% public website coverage.

| Tier | Backend | Auth | Actions |
|------|---------|------|---------|
| 1. Structured data (28) | `yfinance` via `YfData` crumb | no key | quote, history, info, financials, holders, calendar, earnings, dividends, splits, options/options-expiries, recommendations, upgrades, news, search, screener/screener-custom, download, sector/industry, analysis, esg, filings, funds, isin, shares, market, lookup |
| 2. Raw website (5) | Direct Yahoo HTTP (`query1`/`query2` + HTML scrape) | **no crumb, no login** | trending (homepage), chart (v8 bars), ysearch (autocomplete), web-news (topic sections), web-article (full text) |

**Not in scope:** Watchlist / Portfolio / Alerts — auth-gated (Yahoo login cookie).

## Quick start (for an AI agent integrating this)

```bash
git clone https://github.com/lesterppo/hermes-yahoo-finance.git
cd hermes-yahoo-finance
./install.sh ~/.hermes/hermes-agent   # copies tool + skill
```

Then wire the tool into the agent's toolset by adding `yahoo_finance` to `_HERMES_CORE_TOOLS` in `toolsets.py`:

```python
_HERMES_CORE_TOOLS = [
    "web_search", "web_extract", "yahoo_finance",  # ← Web
    ...
]
```

Also appears in `hermes_cli/tools_config.py` as `CONFIGURABLE_TOOLSETS` (on by default).

Restart Hermes. The tool is gated by `check_fn` — it only appears when `import yfinance` succeeds.

### Standalone CLI (no Hermes needed)

```bash
pip install yfinance requests
python cli/yahoo_finance.py quote AAPL
python cli/yahoo_finance.py history AAPL --period 5d --metadata
python cli/yahoo_finance.py analysis AAPL
python cli/yahoo_finance.py funds SPY
python cli/yahoo_finance.py trending --count 5
python cli/yahoo_finance.py chart AAPL --period 1mo --interval 1d
python cli/yahoo_finance.py ysearch "Tesla" --quotes 5 --news 1
python cli/yahoo_finance.py web-news stock-market-news --limit 5
python cli/yahoo_finance.py web-article https://finance.yahoo.com/markets/stocks/articles/...
```

## How the tool works

### Dispatch

Single registry entry `yahoo_finance` with action dispatch. Schema at `tools/yahoo_finance_tool.py` — `YAHOO_FINANCE_SCHEMA`.

```python
yahoo_finance(action="quote", symbol="AAPL")
yahoo_finance(action="history", symbol="AAPL", period="5d", interval="1d", metadata=True)
yahoo_finance(action="financials", symbol="AAPL", statement="income", period="annual")
yahoo_finance(action="holders", symbol="AAPL", kind="institutional")
yahoo_finance(action="trending", region="US", count=5)
yahoo_finance(action="chart", symbol="AAPL", period="5d", interval="1d")
yahoo_finance(action="ysearch", query="Apple", limit=5)
yahoo_finance(action="web-news", topic="stock-market-news", limit=5)
yahoo_finance(action="web-article", url="https://finance.yahoo.com/...", limit=5)
yahoo_finance(action="screener", screener="day_gainers", limit=10)
yahoo_finance(action="screener_custom", query='{"operator":"AND","operands":[...]}')
```

Schema params: `action` (35 values incl. `web_news`/`web_article` aliases), `symbol`/`query`/`screener`/`sector`/`industry`/`market`/`region`/`topic`/`url`/`count`/`limit`/`offset`/`period`/`interval`/`statement`/`kind`/`expiry`/`fields`/`section`/`start`/`end`/`metadata`/`symbols_only`/`quotesCount`/`newsCount`.

Internally: `_build_argv()` → `subprocess.run([sys.executable, CLI, sub, ...], timeout=45)` → passthrough JSON.

### Output format (token-efficient)

```json
{"ok": true, "r": {"symbol": "AAPL", "price": 231.4, "mktCap": 3420000000000}, "symbol": "AAPL"}
{"ok": false, "error": "no ISIN for FAKE_XYZ_999", "symbol": "FAKE_XYZ_999"}
```

Large payloads spill to `~/.hermes/yfinance_output/*.json` with `full_file` + `hint` (info, multi-ticker download). Search/screener cap rows inline.

### All 33 actions

| # | Action | Source | Key args |
|---|--------|--------|----------|
| 1 | `quote` | `get_info()` fast path | `symbol`, `--fields` |
| 2 | `history` | `get_history()` + `get_history_metadata()` | `symbol`, `period` (1d/5d/1mo/…/max), `interval` (1m…3mo), `metadata` bool |
| 3 | `info` | `get_info()` | `symbol`, `section` (quote,profile,stats) |
| 4 | `financials` | `financials`/`quarterly_*`/`ttm_*` | `statement` income\|balance\|cash, `period` annual\|quarterly\|ttm |
| 5 | `holders` | `major/institutional/mutualfund/insider_*` | `kind` all\|major\|institutional\|mutualfund\|insider |
| 6 | `calendar` | `get_calendar()` | `symbol` |
| 7 | `earnings` | `get_earnings_dates()` | `symbol`, `limit` |
| 8 | `dividends` | `dividends` Series | `symbol` |
| 9 | `splits` | `splits` Series | `symbol` |
| 10 | `options-expiries` | `Ticker.options` | `symbol` |
| 11 | `options` | `option_chain(expiry)` | `symbol`, `expiry`, `kind` (calls\|puts), `limit` |
| 12 | `recommendations` | `get_recommendations()` | `symbol` |
| 13 | `upgrades` | `get_upgrades_downgrades()` | `symbol` |
| 14 | `news` | `get_news(count)` | `symbol`, `count`/`limit` |
| 15 | `search` | `yf.Search` | `query`, `limit` |
| 16 | `screener` | `yf.screen(name)` | `screener` (day_gainers, most_actives, …) |
| 17 | `screener-custom` | `yf.screen(EquityQuery)` | `query` JSON body + crumb |
| 18 | `download` | `yf.download(group_by=ticker)` | `symbols` (AAPL,MSFT), `period`, `interval` |
| 19 | `sector` | `yf.Sector(name)` | `name` (technology, healthcare, …) |
| 20 | `industry` | `yf.Industry(name)` | `name` (software-infrastructure, …) |
| 21 | `analysis` | 5 estimate surfaces | `symbol` |
| 22 | `esg` | `get_sustainability()` | `symbol` (often empty → `ok:false`) |
| 23 | `filings` | `get_sec_filings()` | `symbol`, `limit` |
| 24 | `funds` | `FundsData` | `symbol` (ETF/fund only) |
| 25 | `isin` | `get_isin()` | `symbol` |
| 26 | `shares` | `get_shares_full()` | `symbol`, `start`/`end` |
| 27 | `market` | `yf.Market(name)` | `market` (US/GB/ASIA/…) |
| 28 | `lookup` | `yf.Lookup(q)` | `query`, `kind` all\|stock\|etf\|… |
| 29 | `trending` | `GET query2 /v1/finance/trending/{region}` | `region` (US/CA/GB), `count` 1..50, `symbols_only` |
| 30 | `chart` | `GET query1 /v8/finance/chart/{sym}` | `symbol`, `period`, `interval` |
| 31 | `ysearch` | `GET query2 /v1/finance/search?q=` | `query`, `quotesCount`/`newsCount` (or `limit`/`count`) |
| 32 | `web-news` | scrape `/topic/{slug}/` | `topic` (stock-market-news/crypto/earnings/…), `limit` |
| 33 | `web-article` | scrape article URL | `url`, `limit` |

## Testing

```bash
cd ~/.hermes/hermes-agent
scripts/run_tests.sh tests/hermes_cli/test_tools_config.py tests/hermes_cli/test_toolset_validation.py -q
python3 -c "from tools.registry import discover_builtin_tools, r=__import__('tools.registry', fromlist=['registry']).registry; print(discover_builtin_tools())"
yahoo_finance quote AAPL
yahoo_finance trending --count 5
yahoo_finance ysearch "NVDA" --quotes 3
```

## Pitfalls

- `FundsData` is not nullable on equities — every sub-attr raises `No Fund data found`.
- ISIN sentinel `"-"` for invalid tickers — check `isin.strip() == "-"`.
- `get_shares()` is unimplemented — use `get_shares_full(start=...)`.
- `get_sustainability()` empty on most tickers → `ok:false`.
- `Market` valid set is small — only `US` reliably returns `status`.
- `Lookup` API: `yf.Lookup("AI").get_stock()` takes no `query` arg.
- `web-news` valid topics: `stock-market-news`, `latest-news`, `earnings`, `economy`, `personal-finance`, `crypto` (others 404).
- Beyond-yfinance endpoints require **no crumb**; yfinance endpoints need `YfData` crumb.

## Files

```
tools/yahoo_finance_tool.py            # The tool (registry.register + 35-action dispatch)
cli/yahoo_finance.py                   # Standalone CLI (also installed to ~/.hermes/scripts/yahoo-finance/)
skills/yahoo-finance/SKILL.md          # Skill (auto-loaded)
skills/yahoo-finance/references/       # Full-coverage audit + beyond-yfinance + sentinel notes
install.sh                             # Idempotent installer (tool + skill)
AGENTS.md                              # This file
```

## Privacy

No secrets, API keys, or personal paths. All paths via `Path.home() / ".hermes"` / `get_hermes_home()`. Yahoo data is public.
