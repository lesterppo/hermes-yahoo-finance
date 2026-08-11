# Live Probe — 11 Gap Surfaces (2026-08-12)

Probed before coding the 8 new actions. Run this before any yfinance extension.

```python
import yfinance as yf, json
t = yf.Ticker("AAPL")

# 1. analyst_price_targets — dict, always present
t.get_analyst_price_targets()  # {'current': 304.91, 'high': 400.0, ...}

# 2-5. eps_trend / eps_revisions / revenue_estimate / growth_estimates — DFs
t.eps_trend          # DF (4, 6)  — empty check: df.empty
t.eps_revisions      # DF (4, 5)
t.revenue_estimate   # DF (4, 7)
t.growth_estimates   # DF (5, 2)

# 6. sustainability — empty on AAPL/MSFT/TSLA (2026-08-12)
t.get_sustainability()  # DF empty → surface as ok:false

# 7. sec_filings — list of dicts
t.get_sec_filings()  # [{'date': date(2026,7,31), 'type': '10-Q', 'edgarUrl': ...}, ...]  n=79

# 8. funds_data — FundsData object even on equities; sub-attrs raise
fd = yf.Ticker("SPY").funds_data
fd.fund_overview      # dict
fd.top_holdings       # DF (10, 2)
fd.sector_weightings  # dict
fd.equity_holdings    # DF (6, 2)
# AAPL: every fd.* raises "Yahoo API requires funds data ... No Fund data found"

# 9. isin — string; invalid -> "-"
yf.Ticker("AAPL").get_isin()        # "US0378331005"
yf.Ticker("FAKE_XYZ_999").get_isin() # "-"

# 10. shares — get_shares() NotImplemented; use get_shares_full
t.get_shares()  # raises "Have not implemented fetching 'shares'"
t.get_shares_full(start="2020-01-01")  # Series, ~297 rows
# fallback: t.get_info()["sharesOutstanding"]

# 11. history_metadata — dict (not DF)
t.get_history_metadata()  # {'currency':'USD','symbol':'AAPL','exchangeName':'NMS', ...}

# Sector / Industry / Market / Lookup
yf.Sector("technology").overview  # dict (companies_count, market_cap, ...)
yf.Industry("software-infrastructure").overview  # dict (companies_count, ...)
yf.Industry("software-infrastructure").top_companies  # DF (50, 3)
yf.Industry("software-infrastructure").top_growth_companies  # DF
yf.Market("US").status  # {'status':'closed', 'open': datetime, 'close': datetime, ...}
yf.Market("GB").status  # None  (only US reliable)
yf.Lookup("AI").all     # DF (25, 9)
yf.Lookup("AI").get_stock()  # DF — no query arg!  (probe: "got unexpected keyword argument 'query'")
```

Expected live invariants (2026-08-12):
- sustainability empty on all tested equities → don't fake ok:true.
- FundsData non-null on equities but all children error → probe sector_weightings/fund_overview.
- Market GB/ASIA/CURRENCIES → None.
- Lookup.get_* takes zero args.
