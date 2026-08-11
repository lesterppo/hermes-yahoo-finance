# Full-Coverage Audit Recipe (dir → gap table)

1. Enumerate distinct surfaces:

```python
import yfinance as yf
all_attrs = sorted(a for a in dir(yf.Ticker("AAPL")) if not a.startswith("_"))
# normalize aliases away
alias_groups = {
    "income": ["financials","income_stmt","incomestmt","get_income_stmt","get_incomestmt","quarterly_financials","quarterly_incomestmt","ttm_financials","ttm_incomestmt"],
    "balance": ["balance_sheet","balancesheet","get_balance_sheet","get_balancesheet","quarterly_balance_sheet","quarterly_balancesheet"],
    "cash": ["cash_flow","cashflow","get_cash_flow","get_cashflow","quarterly_cash_flow","quarterly_cashflow","ttm_cash_flow","ttm_cashflow"],
}
# After dedup, distinct surfaces ~= 31; CLI had 18 → 11 gaps
```

2. Map to CLI actions. On 2026-08-12, 18 actions covered 14/19 website tabs. Gaps:

   | yfinance surface | website tab | resolution |
   |---|---|---|
   | `analyst_price_targets` + `eps_trend/eps_revisions/revenue_estimate/growth_estimates` | Analysis / Estimates | `analysis` (bundled, 5-in-1) |
   | `sustainability` | Sustainability/ESG | `esg` |
   | `sec_filings` | SEC Filings | `filings` |
   | `funds_data` (8 sub-tables) | ETF/Fund Holdings | `funds` |
   | `get_isin()` | ISIN | `isin` |
   | `get_shares_full()` | Shares | `shares` |
   | `yf.Industry` | Industry drill-down | `industry` |
   | `yf.Market` | Market status | `market` |
   | `yf.Lookup` | Ticker Lookup by quoteType | `lookup` |
   | `get_history_metadata()` | History metadata | `history --metadata` flag (not new action) |

3. Bundling rule: keep schema under ~200 tokens. `analysis` bundles 5 DFs+dict; everything else is 1:1.

4. Non-goals (auth-only, no public endpoint): Watchlist / Portfolio / Conversations / Alerts / paywalled research reports. Note as "out of scope" in the action table.

5. After implementation: `dir(yf.Ticker("AAPL"))` maps 100% of distinct surfaces to either an action or an explicit "out of scope" row. `yahoo_finance --help` shows 28 subparsers; Hermes `YAHOO_FINANCE_SCHEMA` + `_ACTION_MAP` are 28.
