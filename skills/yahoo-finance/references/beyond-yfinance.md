# Beyond yfinance — Raw Yahoo Finance Website Endpoints

Probe date: 2026-08-12. These 5 endpoints are **not wrapped by yfinance** and were added as CLI actions to reach 100% public website coverage (33 total).

## Verified Endpoints (no crumb, no login)

### 1. trending — Homepage "Trending Tickers"

```
GET https://query2.finance.yahoo.com/v1/finance/trending/{region}?count=20&useQuotes=true
# also works on query1
```

- Regions: `US` (default), `CA`, `GB`, … (any Yahoo region). 200 for US; others may 404.
- `count` 1..50 (default 20). `useQuotes=true` returns full quote objects with `trendingScore`, `price`, `market`; `useQuotes=false` returns `{symbol}` only.
- Response: `finance.result[0].quotes[]`. Implementation: `do_trending()` with `_yahoo_get()` helper.
- CLI: `yahoo_finance trending --region US --count 20 [--symbols-only]`
- Tool dispatch: `action=trending, region, count, symbols_only`

### 2. chart — Raw OHLCV via v8 chart

```
GET https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d&includePrePost=false
```

- Works for `AAPL`, `BTC-USD`, `0700.HK`, `GC=F` — no crumb needed (unlike `quoteSummary` which 401s `Invalid Crumb`).
- Response: `chart.result[0]` with `meta` (currency, exchangeName, fullExchangeName, instrumentType, regularMarketPrice, chartPreviousClose, fiftyTwoWeekHigh/Low, `currentTradingPeriod:{pre,regular,post}`) + `timestamp[]` + `indicators.quote[{open,high,low,close,volume}]`.
- Why not just yfinance `history()`? `chart` exposes raw site bars + `meta.currentTradingPeriod` without DataFrame/adjustment overhead. `history` remains for adjusted OHLCV + computed `periodReturnPct`.
- CLI: `yahoo_finance chart AAPL --period 5d --interval 1d`
- Tool dispatch: `action=chart, symbol, period, interval`

### 3. ysearch — Yahoo Autocomplete (fuzzy, scored)

```
GET https://query2.finance.yahoo.com/v1/finance/search?q=Apple&quotesCount=5&newsCount=2&enableFuzzyQuery=false
```

- Richer than `yfinance.Search`: returns `quotes[].score`, `quotes[].sector/industry`, `exchDisp`, fuzzy matches. Verified 200 for `q=Apple` (5 quotes: AAPL, APC.DE, APLE, …).
- CLI: `yahoo_finance ysearch "Apple" --quotes 5 --news 1`
- Tool dispatch: `action=ysearch, query, limit (→quotesCount), count/newsCount`; also supports `quotesCount`/`newsCount` aliases.

### 4. web-news — News by Topic Section

```
HTML scrape https://finance.yahoo.com/topic/{slug}/
```

- Valid slugs (verified 200): `stock-market-news`, `latest-news`, `earnings`, `economy`, `personal-finance`, `crypto`.
- Invalid: `technology` → 404 (the section lives under `/technology/ai/` not `/topic/`). Return 404 with hint: `try: stock-market-news, latest-news, earnings, economy, personal-finance, crypto`.
- No JSON API — must scrape HTML with `requests` + `re` (href regex for `/markets/article/…`, `/economy/…`, etc.). Returns `{title, url}` rows.
- CLI: `yahoo_finance web-news stock-market-news --limit 5`
- Tool dispatch: `action=web-news (alias web_news), topic, limit`

### 5. web-article — Article Text Extract

```
HTML scrape https://finance.yahoo.com/... (any /markets/article/..., /technology/article/..., /live/... URL)
```

- Extract: `<title>` + `<p>` paragraphs joined + `application/ld+json` `articleBody` fallback. Returns `{url, title, text, chars}` (text capped 12000).
- Chained from `web-news` rows: `web-news → rows[0].url → web-article url`.
- CLI: `yahoo_finance web-article https://finance.yahoo.com/markets/stocks/articles/...`
- Tool dispatch: `action=web-article (alias web_article), url (or query/symbol as url)`

## Implementation Notes

- Helper: `_yahoo_get(url, params, timeout=15)` — `requests.get` with `User-Agent: Mozilla/5.0`, `raise_for_status()`, then `r.json()` if `content-type` contains `json` else `{"_raw": r.text[:8000]}`.
- All 5 actions live in the same `yahoo_finance.py` file (single CLI), not a separate plugin. Parser now has 33 subparsers.
- Tool aliases: `web-news`/`web_news`, `web-article`/`web_article` — both accepted by `_ACTION_MAP` and `_build_argv`.
- Auth-gated (out of scope): Watchlist / Portfolio / Alerts — `GET https://query1.finance.yahoo.com/v1/portfolio/...` requires Yahoo login cookie; explain, don't pretend.

## Probe Transcript (abridged)

```
query2 trending US count=5 useQuotes=true → 200, CRWV trendingScore 78.17, SMCI 72.69
v8 chart AAPL range=5d interval=1d → 200, meta {currency:USD, exchangeName:NMS, regularMarketPrice:304.91}
v1 search q=Apple quotesCount=5 → 200, quotes: AAPL (score 41293), APC.DE, APLE, …
topic stock-market-news → 200 len~1.1M, 3 article rows
topic technology → 404 (hint list shown)
article https://.../where-netflix-stock-5-years... → 200, title + 10107 chars
```
