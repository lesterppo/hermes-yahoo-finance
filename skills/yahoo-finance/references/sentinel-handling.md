# Sentinel & Funds Probe Patterns

## ISIN `"-"` sentinel

Invalid tickers do NOT return `None` or `"No Stock Symbol is given"`:

```python
yf.Ticker("FAKE_XYZ_999").get_isin()  # -> "-"
yf.Ticker("AAPL").get_isin()          # -> "US0378331005"
```

Guard:

```python
if not isin or isin == "No Stock Symbol is given" or isin.strip() == "-":
    _err(f"no ISIN for {sym}", symbol=sym)
```

Without this, fake tickers pass as `ok:true` with `isin:"-"`.

## Funds equity-vs-ETF probe

`Ticker.funds_data` is truthy even on equities. Must probe before emitting:

```python
fd = t.funds_data
if fd is None:
    raise ValueError("No Fund data")

# probe — equities raise on every sub-attr
try:
    test = fd.sector_weightings  # property
except Exception:
    test = None
if test is None:
    ov = fd.fund_overview
    if not ov:
        raise ValueError("No Fund data for this symbol (equity/index, not ETF)")

# user-facing error with guidance (not a stack trace)
_err(f"no fund data for {sym} (not an ETF/mutual fund — try SPY, QQQ, VOO)", symbol=sym)
```

Then fan out over 8 attrs: `fund_overview / top_holdings / sector_weightings / equity_holdings / bond_holdings / bond_ratings / asset_classes / fund_operations` — each is either DF (→ `_df_to_compact`) or dict (→ `_j`).

## Other silent-empty surfaces

- `get_sustainability()` → empty DF on all tested equities → return `ok:false`, don't emit empty rows.
- `Market("GB").status` / `Market("ASIA").status` → `None` → `ok:false` with valid-set hint.
