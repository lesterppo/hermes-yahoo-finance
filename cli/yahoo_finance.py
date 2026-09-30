#!/usr/bin/env python3
"""
yahoo_finance — AI-agent-native token-efficient CLI for Yahoo Finance (via yfinance).

Full-function coverage:
    quotes, history, fundamentals, holders, calendar,
options, screener, search, bulk download,
    analysis (estimates/price targets), ESG, filings, funds, ISIN, shares,
    sector/industry, market status, lookup.

Usage:
  yahoo_finance quote AAPL [--fields price,cap,pe]
  yahoo_finance history AAPL --period 1mo [--interval 1d] [--json]
  yahoo_finance info AAPL [--section quote,profile,stats]
  yahoo_finance financials AAPL [--statement income|balance|cash] [--period annual|quarterly|ttm]
  yahoo_finance holders AAPL [--kind major|institutional|mutualfund|insider]
  yahoo_finance calendar AAPL
  yahoo_finance earnings AAPL [--limit 8]
  yahoo_finance dividends AAPL [--period max]
  yahoo_finance splits AAPL
  yahoo_finance options AAPL [--expiry 2026-08-15] [--kind calls|puts|both]
  yahoo_finance options-expiries AAPL
  yahoo_finance recommendations AAPL
  yahoo_finance upgrades AAPL
  yahoo_finance news AAPL [--count 5]
  yahoo_finance search "Apple" [--limit 10]
  yahoo_finance screener day_gainers [--limit 25]
  yahoo_finance screener-custom --query '{"screener":...}' [--limit 25]
  yahoo_finance download AAPL,MSFT --period 1mo [--interval 1d]
  yahoo_finance sector technology  (sector overview)
  yahoo_finance trending  (trending tickers — via screener most_actives)

Output:
    compact JSON to stdout; full DataFrames spilled to file when large.
Exit codes:
    0 ok, 1 usage error, 2 yfinance/API error.
"""
from __future__ import annotations
import argparse
import json
import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

OUTPUT_DIR = Path(os.environ.get("YFINANCE_OUTPUT_DIR", str(Path.home() / ".hermes" / "yfinance_output")))

# ── helpers ──

_PERIOD_DAYS = {"1d": 1, "5d": 5, "1mo": 30, "3mo": 91, "6mo": 182,
                "1y": 365, "2y": 730, "5y": 1825, "10y": 3650}

def _period_start(period: str):
    """Return a cutoff date for a yfinance-style period label, or None."""
    p = (period or "").strip().lower()
    if p == "ytd":
        now = datetime.now(timezone.utc)
        return datetime(now.year, 1, 1, tzinfo=timezone.utc)
    days = _PERIOD_DAYS.get(p)
    if days:
        return datetime.now(timezone.utc) - timedelta(days=days)
    return None

def _ensure_out() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR

def _j(v: Any) -> Any:
    """Make value JSON-serializable."""
    import math
    import decimal
    import pandas as pd
    import numpy as np
    if v is None:
        return None
    if isinstance(v, (bool, int, float, str)):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v
    if isinstance(v, (pd.Timestamp, datetime)):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        if math.isnan(float(v)) or math.isinf(float(v)):
            return None
        return float(v)
    if isinstance(v, np.ndarray):
        return [_j(x) for x in v.tolist()]
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [_j(x) for x in v]
    if isinstance(v, dict):
        return {str(k):
            _j(val) for k, val in v.items()}
    return str(v)

def _df_to_records(df) -> List[Dict]:
    """DataFrame → list of dicts with JSON-safe values."""
    if df is None or len(df) == 0:
        return []
    import pandas as pd
    df2 = df.copy()
    # Flatten index if it's DatetimeIndex
    if isinstance(df2.index, pd.DatetimeIndex):
        df2 = df2.reset_index()
        # Rename first col to 'date' if it's the index
        first = df2.columns[0]
        if first.lower() in ("date", "datetime", "index", "earnings date"):
            df2 = df2.rename(columns={first:
                "date"})
    else:
        df2 = df2.reset_index()
    # Also handle case where index name is set
    records = []
    for _, row in df2.iterrows():
        rec = {}
        for c in df2.columns:
            rec[str(c)] = _j(row[c])
        records.append(rec)
    return records

def _df_to_compact(df, max_rows: int = 50) -> Dict:
    """Return compact summary; spill full to file if large."""
    if df is None or len(df) == 0:
        return {"n":
            0, "rows": []}
    n = len(df)
    recs = _df_to_records(df)
    if n <= max_rows:
        return {"n":
            n, "rows": recs}
    # spill
    p = _ensure_out() / f"yfinance_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.json"
    p.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"n":
        n, "rows": recs[:max_rows], "truncated": True, "full_file": str(p), "hint": f"Full {n} rows at {p}"}

def _ok(data: Any, **extra) -> None:
    out = {"ok":
        True, **extra}
    # data goes under 'r' for token efficiency (like hermes-maxun)
    if isinstance(data, dict) and "error" not in data:
        out["r"] = data
    elif isinstance(data, list):
        out["r"] = data
    elif data is not None:
        out["r"] = data
    # include output file pointer if spill happened
    json.dump(_j(out), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")

def _err(msg: str, code: int = 2, **extra) -> None:
    json.dump({"ok":
        False, "error": msg, **_j(extra)}, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.exit(code)

# ── v2 unified news-item schema (2026-09-30) ──────────────────────────
# Every action that returns news items (news, search, ysearch, web-news)
# emits the same canonical shape:
#   {title, url, publisher, published (ISO), summary, id, kind}
# Fields with no data are omitted (token-minimal). Envelopes
# (symbol/query/topic, n, rows) are unchanged.

def _to_iso_ts(v):
    """Best-effort timestamp -> ISO string (epoch numbers handled)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and v > 0:
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc).isoformat()
        except Exception:
            return v
    return v

def _news_item(title=None, url=None, publisher=None, published=None,
               summary=None, summary_truncated=False, nid=None, kind=None):
    item = {
        "title": title,
        "url": url,
        "publisher": publisher,
        "published": _to_iso_ts(published),
        "summary": summary,
        "id": nid,
        "kind": kind,
    }
    if summary_truncated:
        item["summary_truncated"] = True
    return _j({k: v for k, v in item.items() if v is not None})

# ── action impls ──

def _import_yf():
    try:
        import yfinance as yf
        return yf
    except ImportError as e:
        _err(f"yfinance not installed: {e}. Run: pip install yfinance", code=2)

def do_quote(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    if not sym:
        _err("symbol required", code=1)
    t = yf.Ticker(sym)
    try:
        info = t.get_info()
    except Exception as e:
        _err(f"quote failed for {sym}: {e}", symbol=sym)
    if not info:
        _err(f"no data for symbol {sym} (invalid ticker?)", symbol=sym)
    # yfinance marks unknown/delisted symbols with quoteType "NONE" —
    # fail closed instead of returning ok:true with no price data.
    if str(info.get("quoteType", "")).upper() == "NONE":
        _err(f"no quote for symbol {sym} (invalid ticker or delisted)", symbol=sym)
    # compact fields
    fields = None
    if args.fields:
        fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    # light field map for token efficiency
    key_map = {
        "currentPrice": "price", "regularMarketPrice": "price",
        "previousClose": "prevClose", "open": "open", "dayHigh": "hi", "dayLow": "lo",
        "volume": "vol", "averageVolume": "avgVol", "marketCap": "mktCap",
        "trailingPE": "pe", "forwardPE": "fpe", "dividendYield": "divYieldPct",
        "fiftyTwoWeekHigh": "w52hi", "fiftyTwoWeekLow": "w52lo",
        "fiftyDayAverage": "ma50", "twoHundredDayAverage": "ma200",
        "shortName": "name", "longName": "longName", "symbol": "sym",
        "currency": "ccy", "exchange": "exch", "quoteType": "type",
        "beta": "beta", "trailingEps": "eps", "forwardEps": "fEps",
        "priceToBook": "pb", "enterpriseValue": "ev", "profitMargins": "profitMargin",
        "52WeekChange": "w52chg", "SandP52WeekChange": "sp52chg",
        "earningsTimestamp": "earnTs", "earningsTimestampStart": "earnTs0", "earningsTimestampEnd": "earnTs1",
    }
    if fields:
        # allow both raw and mapped keys (divYield is the legacy alias for divYieldPct)
        rev = {v:
            k for k, v in key_map.items()}
        rev["divYield"] = "dividendYield"
        out = {}
        for f in fields:
            raw = rev.get(f, f)
            if raw in info:
                out[f] = _j(info[raw])
            elif f in info:
                out[f] = _j(info[f])
        if len(out) <= 1:
            # no requested field matched — fail closed like the default path
            _err(f"no matching fields for {sym} (requested: {','.join(fields)})", symbol=sym, fields=fields)
        out["sym"] = sym
        _ok(out, symbol=sym)
        return
    # default compact — detect invalid ticker (info has only nulls / single key)
    out = {"sym":
        sym}
    for raw, short in key_map.items():
        if raw in info and info[raw] is not None:
            out[short] = _j(info[raw])
    for k in ("regularMarketChange", "regularMarketChangePercent", "bid", "ask", "bidSize", "askSize"):
        if k in info and info[k] is not None:
            out[k] = _j(info[k])
    # If only sym survived, the ticker is invalid / no quote
    if len(out) <= 1:
        # check if yfinance returned essentially empty info
        non_null = sum(1 for v in info.values() if v is not None)
        if non_null <= 1:
            _err(f"no quote for symbol {sym} (invalid ticker or delisted)", symbol=sym)
    _ok(out, symbol=sym)

def do_history(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    if not sym:
        _err("symbol required", code=1)
    valid_periods = {"1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"}
    valid_intervals = {"1m","2m","5m","15m","30m","60m","90m","1h","1d","5d","1wk","1mo","3mo"}
    period = (args.period or "1mo").strip()
    interval = (args.interval or "1d").strip()
    if period not in valid_periods:
        _err(f"invalid period '{period}'; valid: {sorted(valid_periods)}", code=1)
    if interval not in valid_intervals:
        _err(f"invalid interval '{interval}'; valid: {sorted(valid_intervals)}", code=1)
    t = yf.Ticker(sym)
    try:
        auto_adj = not args.no_adjust
        df = t.history(period=period, interval=interval, auto_adjust=auto_adj, actions=args.actions)
    except Exception as e:
        _err(f"history failed for {sym}: {e}", symbol=sym, period=period, interval=interval)
    if df is None or len(df) == 0:
        _err(f"no history for {sym} period={period} interval={interval}", symbol=sym)
    # add computed returns if daily+
    recs = _df_to_records(df)
    # optionally include summary stats
    if len(recs) >= 2:
        try:
            closes = [r.get("Close") for r in recs if r.get("Close") is not None]
            if len(closes) >= 2 and closes[0]:
                ret = (closes[-1] - closes[0]) / closes[0] * 100
                chg = closes[-1] - closes[0]
            else:
                ret = chg = None
        except Exception:
            ret = chg = None
    else:
        ret = chg = None
    meta = {"symbol":
        sym, "period": period, "interval": interval, "n": len(recs)}
    # optional history_metadata (exchange, timezone, etc.) — website History tab metadata
    if getattr(args, "metadata", False):
        try:
            hm = t.get_history_metadata()  # type: ignore[attr-defined]
            if hm:
                meta["history_metadata"] = _j(hm)
        except Exception:
            pass
    if ret is not None:
        meta["periodReturnPct"] = round(ret, 2)
        meta["periodChange"] = round(chg, 4) if chg is not None else None
    # spill handling
    limit = args.limit or 100
    if len(recs) > limit:
        p = _ensure_out() / f"history_{sym}_{period}_{interval}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.json"
        p.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
        _ok({"meta":
            meta, "rows": recs[-limit:], "truncated": True, "truncated_from": "oldest", "full_file": str(p), "hint": f"Full {len(recs)} rows at {p}"}, symbol=sym)
    else:
        _ok({"meta":
            meta, "rows": recs}, symbol=sym)

def do_info(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    if not sym:
        _err("symbol required", code=1)
    t = yf.Ticker(sym)
    try:
        info = t.get_info()
    except Exception as e:
        _err(f"info failed for {sym}: {e}", symbol=sym)
    if not info:
        _err(f"no info for {sym}", symbol=sym)
    # sections
    sections = {
        "quote": ["symbol","shortName","longName","currentPrice","regularMarketPrice","previousClose","open","dayHigh","dayLow","volume","averageVolume","marketCap","trailingPE","forwardPE","dividendYield","fiftyTwoWeekHigh","fiftyTwoWeekLow","fiftyDayAverage","twoHundredDayAverage","beta","currency","exchange","quoteType","regularMarketChange","regularMarketChangePercent","bid","ask","priceToBook","enterpriseValue","trailingEps","forwardEps","52WeekChange","SandP52WeekChange"],
        "profile": ["address1","city","state","zip","country","phone","website","industry","industryKey","industryDisp","sector","sectorKey","sectorDisp","longBusinessSummary","fullTimeEmployees","companyOfficers"],
        "stats": ["auditRisk","boardRisk","compensationRisk","shareHolderRightsRisk","overallRisk","governanceScores","earningsTimestamp","earningsTimestampStart","earningsTimestampEnd","exDividendDate","dividendRate","payoutRatio","profitMargins","grossMargins","operatingMargins","returnOnAssets","returnOnEquity","revenueGrowth","earningsGrowth","revenuePerShare","totalCash","totalCashPerShare","totalDebt","debtToEquity","currentRatio","quickRatio","cashPerShare","bookValue","priceToBook"],
    }
    want = None
    if args.section:
        want = [s.strip() for s in args.section.split(",") if s.strip()]
        bad = [s for s in want if s not in sections]
        if bad:
            _err(f"invalid section(s) {bad}; valid: {list(sections)}", code=1)
    if want:
        keys = []
        for s in want:
            keys.extend(sections[s])
        out = {k:
            _j(info[k]) for k in keys if k in info and info[k] is not None}
        out["_symbol"] = sym
        _ok(out, symbol=sym, sections=want)
        return
    # no filter → return compact + spill raw
    # keep full info as spill file for agent
    p = _ensure_out() / f"info_{sym}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.json"
    p.write_text(json.dumps(_j(info), ensure_ascii=False, indent=2), encoding="utf-8")
    # compact preview
    preview_keys = sections["quote"][:14]
    preview = {k:
        _j(info[k]) for k in preview_keys if k in info and info[k] is not None}
    preview["_symbol"] = sym
    _ok({"preview":
        preview, "full_file": str(p), "total_keys": len(info), "hint": f"Full info ({len(info)} keys) at {p}"}, symbol=sym)

def do_financials(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    stmt = (args.statement or "income").lower()
    period = (args.period or "annual").lower()
    if stmt not in ("income","balance","cash"):
        _err("statement must be income|balance|cash", code=1)
    if period not in ("annual","quarterly","ttm"):
        _err("period must be annual|quarterly|ttm", code=1)
    if stmt == "balance" and period == "ttm":
        _err("ttm is not meaningful for the balance sheet (point-in-time snapshot); use annual|quarterly",
             code=1, symbol=sym, statement=stmt, period=period)
    t = yf.Ticker(sym)
    try:
        if stmt == "income":
            if period == "annual":
                df = t.financials
            elif period == "quarterly":
                df = t.quarterly_financials
            else:
                df = t.ttm_financials
        elif stmt == "balance":
            if period == "annual":
                df = t.balance_sheet
            elif period == "quarterly":
                df = t.quarterly_balance_sheet
            else:
                df = t.balance_sheet  # ttm balance not distinct
        else:  # cash
            if period == "annual":
                df = t.cashflow
            elif period == "quarterly":
                df = t.quarterly_cashflow
            else:
                df = t.ttm_cashflow
    except Exception as e:
        _err(f"financials failed for {sym}: {e}", symbol=sym, statement=stmt, period=period)
    if df is None or (hasattr(df, "empty") and df.empty):
        _err(f"no {stmt} {period} data for {sym}", symbol=sym, statement=stmt, period=period)
    # yfinance financials: index=line items, columns=dates
    # Transpose for row-per-period compact form
    try:
        df_t = df.T  # dates as rows
        recs = _df_to_records(df_t)
        # row labels are dates
        cols = [str(c) for c in df.index.tolist()]
    except Exception as e:
        _err(f"financials parse failed for {sym}: {e}", symbol=sym)
    meta = {"symbol":
        sym, "statement": stmt, "period": period, "n_periods": len(recs), "line_items": cols[:30]}
    if len(cols) > 30:
        meta["line_items_truncated"] = True
        meta["total_line_items"] = len(cols)
    p = _ensure_out() / f"financials_{sym}_{stmt}_{period}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.json"
    p.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    # preview: first 2 periods, first 8 line items
    preview = []
    for r in recs[:2]:
        pr = {k:
            r[k] for k in list(r.keys())[:9]}
        preview.append(pr)
    _ok({"meta":
        meta, "preview": preview, "full_file": str(p)}, symbol=sym)

def do_holders(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    kind = (args.kind or "all").lower()
    if kind not in ("all","major","institutional","mutualfund","insider"):
        _err("kind must be all|major|institutional|mutualfund|insider", code=1)
    t = yf.Ticker(sym)
    out: Dict[str, Any] = {"symbol": sym}
    try:
        if kind in ("all","major"):
            mh = t.major_holders
            if mh is not None and not mh.empty:
                # major_holders is a small DF with Breakdown/Value
                out["major"] = _df_to_records(mh)
            else:
                out["major"] = []
        if kind in ("all","institutional"):
            ih = t.institutional_holders
            out["institutional"] = _df_to_records(ih) if ih is not None and len(ih) else []
        if kind in ("all","mutualfund"):
            mf = t.mutualfund_holders
            out["mutualfund"] = _df_to_records(mf) if mf is not None and len(mf) else []
        if kind in ("all","insider"):
            it = t.insider_transactions
            ir = t.insider_roster_holders if hasattr(t, "insider_roster_holders") else None
            it2 = t.insider_purchases if hasattr(t, "insider_purchases") else None
            out["insider_transactions"] = _df_to_records(it) if it is not None and len(it) else []
            if ir is not None and hasattr(ir, "__len__") and len(ir):
                out["insider_roster"] = _df_to_records(ir)
            if it2 is not None and hasattr(it2, "__len__") and len(it2):
                out["insider_purchases"] = _df_to_records(it2)
    except Exception as e:
        _err(f"holders failed for {sym}: {e}", symbol=sym, kind=kind)
    _ok(out, symbol=sym, kind=kind)

def do_calendar(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    t = yf.Ticker(sym)
    try:
        cal = t.get_calendar()
    except Exception as e:
        _err(f"calendar failed for {sym}: {e}", symbol=sym)
    if cal is None or (isinstance(cal, dict) and not cal):
        _err(f"no calendar for {sym}", symbol=sym)
    # cal is dict
    _ok(_j(cal), symbol=sym)

def do_earnings(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    t = yf.Ticker(sym)
    try:
        df = t.get_earnings_dates(limit=args.limit or 8)
    except Exception as e:
        _err(f"earnings failed for {sym}: {e}", symbol=sym)
    if df is None or len(df) == 0:
        _err(f"no earnings dates for {sym}", symbol=sym)
    recs = _df_to_records(df)
    _ok({"symbol":
        sym, "n": len(recs), "rows": recs}, symbol=sym)

def do_dividends(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    period = (args.period or "max").strip()
    t = yf.Ticker(sym)
    try:
        s = t.dividends
        # honor --period by slicing the date-indexed series
        if period != "max" and s is not None and len(s):
            cutoff = _period_start(period)
            if cutoff is not None:
                # dividends index may be tz-aware or naive — compare naively
                idx = s.index
                cut = cutoff
                if getattr(idx, "tz", None) is not None:
                    idx = idx.tz_localize(None)
                    cut = cutoff.replace(tzinfo=None)
                s = s[idx >= cut]
            # unrecognized period label: keep full history (period echoed in output)
        if s is None or len(s) == 0:
            _ok({"symbol":
                sym, "n": 0, "rows": []}, symbol=sym)
            return
        df = s.reset_index()
        df.columns = ["date", "dividend"]
        recs = _df_to_records(df)
    except Exception as e:
        _err(f"dividends failed for {sym}: {e}", symbol=sym)
    _ok({"symbol":
        sym, "period": period, "n": len(recs), "rows": recs[-50:] if len(recs) > 50 else recs, "total": len(recs)}, symbol=sym)

def do_splits(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    t = yf.Ticker(sym)
    try:
        s = t.splits
        if s is None or len(s) == 0:
            _ok({"symbol":
                sym, "n": 0, "rows": []}, symbol=sym)
            return
        df = s.reset_index()
        df.columns = ["date", "ratio"]
        recs = _df_to_records(df)
    except Exception as e:
        _err(f"splits failed for {sym}: {e}", symbol=sym)
    _ok({"symbol":
        sym, "n": len(recs), "rows": recs}, symbol=sym)

def do_options_expiries(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    t = yf.Ticker(sym)
    try:
        exps = t.options
    except Exception as e:
        _err(f"options expiries failed for {sym}: {e}", symbol=sym)
    if not exps:
        _err(f"no options for {sym}", symbol=sym)
    _ok({"symbol":
        sym, "n": len(exps), "expiries": list(exps)}, symbol=sym)

def do_options(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    t = yf.Ticker(sym)
    try:
        exps = t.options
    except Exception as e:
        _err(f"options failed for {sym}: {e}", symbol=sym)
    if not exps:
        _err(f"no options for {sym}", symbol=sym)
    expiry = args.expiry
    if not expiry:
        expiry = exps[0]
    if expiry not in exps:
        _err(f"expiry {expiry} not in {list(exps)[:10]}... (n={len(exps)})", code=1, symbol=sym, expiry=expiry)
    kind = (args.kind or "both").lower()
    if kind not in ("calls","puts","both"):
        _err("kind must be calls|puts|both", code=1)
    try:
        chain = t.option_chain(expiry)
    except Exception as e:
        _err(f"option_chain failed for {sym} {expiry}: {e}", symbol=sym, expiry=expiry)
    out: Dict[str, Any] = {"symbol": sym, "expiry": expiry}
    # truncate large chains
    max_rows = args.limit or 30
    if kind in ("calls","both"):
        calls = chain.calls
        recs = _df_to_records(calls)
        if len(recs) > max_rows:
            p = _ensure_out() / f"options_{sym}_{expiry}_calls_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.json"
            p.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
            out["calls"] = {"n":
                len(recs), "rows": recs[:max_rows], "truncated": True, "full_file": str(p)}
        else:
            out["calls"] = {"n":
                len(recs), "rows": recs}
    if kind in ("puts","both"):
        puts = chain.puts
        recs = _df_to_records(puts)
        if len(recs) > max_rows:
            p = _ensure_out() / f"options_{sym}_{expiry}_puts_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.json"
            p.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
            out["puts"] = {"n":
                len(recs), "rows": recs[:max_rows], "truncated": True, "full_file": str(p)}
        else:
            out["puts"] = {"n":
                len(recs), "rows": recs}
    _ok(out, symbol=sym, expiry=expiry)

def do_recommendations(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    t = yf.Ticker(sym)
    try:
        df = t.get_recommendations()
        summary = t.get_recommendations_summary()
    except Exception as e:
        _err(f"recommendations failed for {sym}: {e}", symbol=sym)
    out: Dict[str, Any] = {"symbol": sym}
    if df is not None and len(df):
        out["history"] = _df_to_records(df.tail(12))
        out["history_n"] = len(df)
    if summary is not None and isinstance(summary, dict) and summary:
        out["summary"] = _j(summary)
    elif summary is not None and hasattr(summary, "empty") and not summary.empty:
        out["summary"] = _df_to_records(summary)
    if not out.get("history") and not out.get("summary"):
        _err(f"no recommendations for {sym}", symbol=sym)
    _ok(out, symbol=sym)

def do_upgrades(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    t = yf.Ticker(sym)
    try:
        df = t.get_upgrades_downgrades()
    except Exception as e:
        _err(f"upgrades failed for {sym}: {e}", symbol=sym)
    if df is None or len(df) == 0:
        _err(f"no upgrades/downgrades for {sym}", symbol=sym)
    # df indexed by date
    recs = _df_to_records(df.tail(30))
    _ok({"symbol":
        sym, "n": len(df), "rows": recs}, symbol=sym)

def do_news(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    t = yf.Ticker(sym)
    try:
        items = t.get_news(count=args.count or 5)
    except Exception as e:
        _err(f"news failed for {sym}: {e}", symbol=sym)
    if not items:
        _err(f"no news for {sym}", symbol=sym)
    rows = []
    for it in items[:
        args.count or 5]:
        c = it.get("content", {}) if isinstance(it, dict) else {}
        _summary = (c.get("summary") or c.get("description") or "")
        _truncated = len(_summary) > 300
        _url = (c.get("clickThroughUrl", {}).get("url") if isinstance(c.get("clickThroughUrl"), dict) else c.get("clickThroughUrl")
                or c.get("canonicalUrl", {}).get("url") if isinstance(c.get("canonicalUrl"), dict) else None)
        _provider = (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict) else None
        rows.append(_news_item(
            title=c.get("title"),
            url=_url,
            publisher=_provider,
            published=c.get("pubDate") or c.get("displayTime"),
            summary=_summary[:300] + ("…" if _truncated else ""),
            summary_truncated=_truncated,
            nid=it.get("id"),
            kind=c.get("contentType"),
        ))
    _ok({"symbol":
        sym, "n": len(rows), "rows": rows}, symbol=sym)

def do_search(args):
    yf = _import_yf()
    q = args.query.strip()
    if not q:
        _err("query required", code=1)
    try:
        s = yf.Search(q, max_results=args.limit or 10)
        quotes = getattr(s, "quotes", []) or []
        news = getattr(s, "news", []) or []
    except Exception as e:
        _err(f"search failed for '{q}': {e}", query=q)
    rows = []
    for qu in quotes[:
        args.limit or 10]:
        rows.append(_j({k:
            qu[k] for k in ("symbol","shortname","longname","exchange","quoteType","typeDisp","sector","industry","exchDisp") if k in qu}))
    out: Dict[str, Any] = {"query": q, "n": len(rows), "rows": rows}
    if news:
        out["news_n"] = len(news)
        out["news_preview"] = [_news_item(
            title=n.get("title") if isinstance(n, dict) else None,
            url=n.get("link") if isinstance(n, dict) else None,
            publisher=n.get("publisher") if isinstance(n, dict) else None,
            published=n.get("providerPublishTime") if isinstance(n, dict) else None,
            nid=n.get("uuid") if isinstance(n, dict) else None,
            kind=n.get("type") if isinstance(n, dict) else None,
        ) for n in news[:2]]
    if not rows:
        _err(f"no results for '{q}'", query=q)
    _ok(out, query=q)

def do_screener(args):
    _import_yf()
    name = args.name.strip()
    if not name:
        _err("screener name required", code=1)
    limit = args.limit or 25
    offset = args.offset or 0
    try:
        # private import kept inside try so a yfinance-internal move
        # surfaces as a clean JSON error, not a traceback
        from yfinance.screener.screener import PREDEFINED_SCREENER_QUERIES
        if name not in PREDEFINED_SCREENER_QUERIES:
            _err(f"unknown screener '{name}'; valid: {sorted(PREDEFINED_SCREENER_QUERIES)}", screener=name, code=1)
        import yfinance as _yf2
        # Use yfinance's own screen() which handles crumb+cookies via YfData
        if offset:
            # predefined endpoint ignores offset → use query-based path
            from yfinance.screener.screener import PREDEFINED_SCREENER_QUERIES as Q
            qobj = Q[name]["query"]
            sortField = Q[name].get("sortField", "dayvolume")
            sortAsc = Q[name].get("sortType", "DESC").lower() == "asc"
            result = _yf2.screen(qobj, offset=offset, size=limit, sortField=sortField, sortAsc=sortAsc)
        else:
            result = _yf2.screen(name, count=limit)
        quotes = result.get("quotes", []) if isinstance(result, dict) else []
        if not quotes:
            _err(f"screener '{name}' returned 0 results (Yahoo may have throttled)", screener=name)
    except SystemExit:
        raise
    except Exception as e:
        _err(f"screener '{name}' failed: {e}", screener=name)
    rows = []
    for q in quotes[:limit]:
        rows.append(_j({k:
            q[k] for k in ("symbol","shortname","longname","regularMarketPrice","regularMarketChange","regularMarketChangePercent","regularMarketVolume","marketCap","trailingPE","dividendYield","fiftyTwoWeekHigh","fiftyTwoWeekLow","exchange","quoteType") if k in q}))
    _ok({"screener":
        name, "n": len(rows), "offset": offset, "rows": rows}, screener=name)

def do_screener_custom(args):
    import json as _json
    qstr = args.query.strip()
    if not qstr:
        _err("--query JSON required", code=1)
    try:
        body = _json.loads(qstr)
    except Exception as e:
        _err(f"invalid --query JSON: {e}", code=1)
    limit = args.limit or 25
    offset = args.offset or 0
    try:
        import yfinance as _yf3
        from yfinance import EquityQuery
        # body is expected to be {operator, operands} or full {query, sortField, ...}
        # Use yfinance's authenticated YfData path (handles crumb/cookies)
        def _dict_to_query(d):
            if isinstance(d, dict) and "operator" in d:
                ops = []
                for o in d.get("operands", []):
                    if isinstance(o, dict) and "operator" in o:
                        ops.append(_dict_to_query(o))
                    else:
                        ops.append(o)
                return EquityQuery(d["operator"], ops)
            return d
        q_obj = None
        sortField = body.get("sortField", "dayvolume") if isinstance(body, dict) and "operator" not in body else "dayvolume"
        sortAsc = (body.get("sortType", "DESC").lower() == "asc") if isinstance(body, dict) and "operator" not in body else False
        if isinstance(body, dict) and "operator" in body:
            q_obj = _dict_to_query(body)
        elif isinstance(body, dict) and "query" in body:
            qd = body["query"]
            if isinstance(qd, dict) and "operator" in qd:
                q_obj = _dict_to_query(qd)
                sortField = body.get("sortField", sortField)
                sortAsc = body.get("sortType", "DESC").lower() == "asc"
            else:
                q_obj = EquityQuery("and", [EquityQuery("eq", ["region","us"])])
        else:
            q_obj = EquityQuery("and", [EquityQuery("eq", ["region","us"])])
        result = _yf3.screen(q_obj, size=limit, offset=offset, sortField=sortField, sortAsc=sortAsc)
        quotes = result.get("quotes", []) if isinstance(result, dict) else []
        if not quotes:
            _err("custom screener returned 0 results", query=body)
    except SystemExit:
        raise
    except Exception as e:
        _err(f"custom screener failed: {e}", query=body)
    rows = []
    for q in quotes[:limit]:
        rows.append(_j({k:
            q[k] for k in ("symbol","shortname","longname","regularMarketPrice","regularMarketChange","regularMarketChangePercent","regularMarketVolume","marketCap","trailingPE","exchange","quoteType") if k in q}))
    _ok({"custom":
        True, "n": len(rows), "offset": offset, "rows": rows})

def do_download(args):
    _import_yf()
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not syms:
        _err("symbols required (comma-separated)", code=1)
    period = (args.period or "1mo").strip()
    interval = (args.interval or "1d").strip()
    import yfinance as _yf
    try:
        df = _yf.download(syms if len(syms) > 1 else syms[0], period=period, interval=interval, group_by="ticker", auto_adjust=True, progress=False, threads=True)
    except Exception as e:
        _err(f"download failed: {e}", symbols=syms)
    if df is None or len(df) == 0:
        _err(f"no data for {syms}", symbols=syms)
    # Normalize: multi-ticker → columns are MultiIndex
    import pandas as pd
    out: Dict[str, Any] = {"symbols": syms, "period": period, "interval": interval, "n": len(df)}
    if isinstance(df.columns, pd.MultiIndex):
        # group_by ticker → top-level is ticker
        tickers = list(df.columns.get_level_values(0).unique())
        out["tickers"] = tickers
        # preview: last 3 rows per ticker (compact)
        preview = {}
        for tk in tickers[:5]:
            sub = df[tk].tail(5)
            preview[tk] = _df_to_records(sub.reset_index())
        out["preview"] = preview
        if len(df) > 5 or len(tickers) > 5:
            p = _ensure_out() / f"download_{'_'.join(syms[:3])}_{period}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.json"
            # flatten for file
            flat = df.reset_index()
            # convert MultiIndex columns to strings
            flat.columns = ["_".join([str(x) for x in c if x]) if isinstance(c, tuple) else str(c) for c in flat.columns]
            recs = _df_to_records(flat)
            p.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
            out["full_file"] = str(p)
            out["hint"] = f"Full {len(df)} rows at {p}"
    else:
        recs = _df_to_records(df.reset_index())
        out["rows"] = recs[-10:] if len(recs) > 10 else recs
        if len(recs) > 10:
            p = _ensure_out() / f"download_{syms[0]}_{period}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.json"
            p.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
            out["full_file"] = str(p)
    _ok(out, symbols=syms)

def do_sector(args):
    # Sector overview via yfinance Sector
    _import_yf()
    name = (args.name or "").strip().lower().replace(" ", "-")
    if not name:
        _err("sector name required (e.g. technology, healthcare, financial-services)", code=1)
    try:
        from yfinance import Sector
        s = Sector(name)
        ov = s.overview
        top = s.top_companies
        etfs = s.top_etfs
    except Exception as e:
        _err(f"sector '{name}' failed: {e}", sector=name)
    out: Dict[str, Any] = {"sector": name}
    if ov is not None and isinstance(ov, dict):
        out["overview"] = _j(ov)
    elif ov is not None:
        out["overview"] = _j(str(ov)[:2000])
    if top is not None and hasattr(top, "__len__") and len(top):
        try:
            out["top_companies"] = _df_to_records(top) if hasattr(top, "columns") else _j(top)
        except Exception:
            out["top_companies"] = _j(str(top)[:4000])
    if etfs is not None and hasattr(etfs, "__len__") and len(etfs):
        try:
            out["top_etfs"] = _df_to_records(etfs) if hasattr(etfs, "columns") else _j(etfs)
        except Exception:
            out["top_etfs"] = _j(str(etfs)[:4000])
    if not out.get("overview") and not out.get("top_companies"):
        _err(f"no data for sector '{name}'", sector=name)
    _ok(out, sector=name)

# ── Full-coverage add-ons ──

def do_analysis(args):
    """Bundles analyst estimates: price targets, EPS trend/revisions, revenue & growth."""
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    if not sym:
        _err("symbol required", code=1)
    t = yf.Ticker(sym)
    out: Dict[str, Any] = {"symbol": sym}
    unavailable = []
    try:
        pt = t.get_analyst_price_targets()
        if pt:
            out["price_targets"] = _j(pt)
    except Exception:
        unavailable.append("price_targets")
    for attr, key in [
        ("eps_trend", "eps_trend"),
        ("eps_revisions", "eps_revisions"),
        ("revenue_estimate", "revenue_estimate"),
        ("growth_estimates", "growth_estimates"),
    ]:
        try:
            df = getattr(t, attr, None)
            if df is not None and hasattr(df, "empty") and not df.empty:
                out[key] = _df_to_records(df)
            elif df is not None and hasattr(df, "__len__") and len(df):
                out[key] = _j(df) if isinstance(df, dict) else _df_to_records(df)  # type: ignore[arg-type]
        except Exception:
            unavailable.append(key)
    if len(out) <= 1:
        _err(f"no analysis data for {sym} (may be an ETF/index without analyst coverage)", symbol=sym)
    if unavailable:
        out["unavailable"] = unavailable
    _ok(out, symbol=sym)


def do_esg(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    t = yf.Ticker(sym)
    try:
        df = t.get_sustainability()
    except Exception as e:
        _err(f"sustainability failed for {sym}: {e}", symbol=sym)
    if df is None or (hasattr(df, "empty") and df.empty):
        _err(f"no ESG/sustainability data for {sym}", symbol=sym)
    # sustainability is a DF in yfinance (transposed)
    _ok({"symbol": sym, **_j(_df_to_compact(df, max_rows=80))}, symbol=sym)


def do_filings(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    t = yf.Ticker(sym)
    try:
        rows = t.get_sec_filings()
    except Exception as e:
        _err(f"sec_filings failed for {sym}: {e}", symbol=sym)
    if not rows:
        _err(f"no SEC filings for {sym}", symbol=sym)
    # rows is a list of dicts
    limit = args.limit or 20
    preview = [_j(r) for r in rows[:limit]]
    p = None
    if len(rows) > limit:
        p = _ensure_out() / f"filings_{sym}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.json"
        p.write_text(json.dumps([_j(r) for r in rows], ensure_ascii=False, indent=2), encoding="utf-8")
    _ok({"symbol": sym, "n": len(rows), "rows": preview, **({"full_file": str(p), "hint": f"Full {len(rows)} filings at {p}"} if p else {})}, symbol=sym)


def do_funds(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    t = yf.Ticker(sym)
    try:
        fd = t.funds_data
        if fd is None:
            raise ValueError("No Fund data")
        # Probe one attribute to verify fund coverage (equities return FundsData object but all sub-calls fail)
        # Try sector_weightings first
        test = None
        try:
            test = fd.sector_weightings  # property
        except Exception:
            test = None
        if test is None:
            # double-check via fund_overview
            ov = fd.fund_overview
            if not ov:
                raise ValueError("No Fund data for this symbol (equity/index, not an ETF/mutual fund)")
    except Exception as e:
        msg = str(e)
        if "No Fund data" in msg:
            _err(f"no fund data for {sym} (not an ETF/mutual fund — try SPY, QQQ, VOO)", symbol=sym)
        _err(f"funds failed for {sym}: {e}", symbol=sym)
    out: Dict[str, Any] = {"symbol": sym}
    mapping = [
        ("fund_overview", "fund_overview"),
        ("top_holdings", "top_holdings"),
        ("sector_weightings", "sector_weightings"),
        ("equity_holdings", "equity_holdings"),
        ("bond_holdings", "bond_holdings"),
        ("bond_ratings", "bond_ratings"),
        ("asset_classes", "asset_classes"),
        ("fund_operations", "fund_operations"),
    ]
    failed = []
    for attr, key in mapping:
        try:
            v = getattr(fd, attr, None)
            if v is None:
                continue
            if hasattr(v, "columns"):
                df = v
                # yfinance labels the weight column "Holding Percent" but
                # stores fractions (0.0808); scale so the label is true.
                if "Holding Percent" in df.columns:
                    df = df.copy()
                    df["Holding Percent"] = (df["Holding Percent"] * 100).round(4)
                out[key] = _j(_df_to_compact(df, max_rows=30))
            elif isinstance(v, dict) and v:
                out[key] = _j(v)
            elif v:
                out[key] = _j(v)
        except Exception:
            failed.append(attr)
    if len(out) <= 1:
        _err(f"no fund data for {sym}", symbol=sym)
    if failed:
        out["unavailable"] = failed
    _ok(out, symbol=sym)


def do_isin(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    t = yf.Ticker(sym)
    try:
        isin = t.get_isin()
    except Exception as e:
        _err(f"isin failed for {sym}: {e}", symbol=sym)
    if not isin or isin == "No Stock Symbol is given" or isin.strip() == "-":
        _err(f"no ISIN for {sym}", symbol=sym)
    _ok({"symbol": sym, "isin": isin}, symbol=sym)


def do_shares(args):
    yf = _import_yf()
    sym = args.symbol.strip().upper()
    t = yf.Ticker(sym)
    start = (args.start or "").strip() or None
    end = (args.end or "").strip() or None
    try:
        s = t.get_shares_full(start=start, end=end) if (start or end) else t.get_shares_full(start="2020-01-01")
    except Exception as e:
        msg = str(e)
        if "shares" in msg.lower():
            # Fallback: try via history / info if get_shares_full unavailable
            try:
                info = t.get_info()
                shares_out = info.get("sharesOutstanding")
                if shares_out:
                    _ok({"symbol": sym, "sharesOutstanding": shares_out, "source": "info.sharesOutstanding"}, symbol=sym)
                    return
            except Exception:
                pass
        _err(f"shares failed for {sym}: {e}", symbol=sym)
    if s is None or len(s) == 0:
        _err(f"no shares data for {sym}", symbol=sym)
    df = s.reset_index()
    df.columns = ["date", "shares"]
    recs = _df_to_records(df)
    limit = args.limit or 50
    preview = recs[-limit:] if len(recs) > limit else recs
    out: Dict[str, Any] = {"symbol": sym, "n": len(recs), "rows": preview}
    if len(recs) > limit:
        p = _ensure_out() / f"shares_{sym}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.json"
        p.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
        out["full_file"] = str(p)
    _ok(out, symbol=sym)


def do_industry(args):
    _import_yf()
    name = (args.name or args.symbol or "").strip().lower().replace(" ", "-")
    if not name:
        _err("industry name required (e.g. software-infrastructure, semiconductors, banks-diversified)", code=1)
    try:
        from yfinance import Industry
        ind = Industry(name)
        ov = ind.overview
        top = ind.top_companies
    except Exception as e:
        _err(f"industry '{name}' failed: {e}", sector=name)
    out: Dict[str, Any] = {"industry": name}
    if ov is not None and isinstance(ov, dict):
        out["overview"] = _j(ov)
    elif ov is not None:
        out["overview"] = _j(str(ov)[:2000])
    if top is not None and hasattr(top, "__len__") and len(top):
        try:
            out["top_companies"] = _df_to_records(top) if hasattr(top, "columns") else _j(top)
        except Exception:
            out["top_companies"] = _j(str(top)[:4000])
    # also expose top_growth / top_performing if available
    for extra in ("top_growth_companies", "top_performing_companies"):
        try:
            v = getattr(ind, extra, None)
            if v is not None and hasattr(v, "__len__") and len(v):
                out[extra] = _df_to_records(v) if hasattr(v, "columns") else _j(v)
        except Exception:
            pass
    if not out.get("overview") and not out.get("top_companies"):
        _err(f"no data for industry '{name}'", sector=name)
    _ok(out, sector=name)


def do_market(args):
    _import_yf()
    name = (args.name or "US").strip().upper()
    # normalize: us_market -> US, etc.
    alias = {"US_MARKET": "US", "US MARKET": "US", "USA": "US"}
    name = alias.get(name, name)
    try:
        from yfinance import Market
        m = Market(name)
        status = m.status
    except Exception as e:
        _err(f"market '{name}' failed: {e}", region=name)
    if status is None:
        _err(f"no market status for '{name}' (valid: US, GB, ASIA, EUROPE, RATES, COMMODITIES, CURRENCIES, CRYPTOCURRENCIES)", region=name)
    _ok({"market": name, "status": _j(status)}, region=name)


def do_lookup(args):
    yf = _import_yf()
    q = (args.query or "").strip()
    if not q:
        _err("query required", code=1)
    kind = (args.kind or "all").lower()
    if kind not in ("all", "stock", "etf", "mutualfund", "index", "future", "currency", "cryptocurrency"):
        _err("kind must be all|stock|etf|mutualfund|index|future|currency|cryptocurrency", code=1)
    try:
        lk = yf.Lookup(q)
        if kind == "all":
            df = lk.all
        else:
            df = getattr(lk, f"get_{kind}")()
            # get_* may be a property or method returning DF
            if callable(df):
                df = df()
    except Exception as e:
        _err(f"lookup failed for '{q}': {e}", query=q)
    if df is None or (hasattr(df, "empty") and df.empty):
        _err(f"no lookup results for '{q}' kind={kind}", query=q)
    recs = _df_to_records(df)
    limit = args.limit or 25
    preview = recs[:limit]
    _ok({"query": q, "kind": kind, "n": len(recs), "rows": preview}, query=q)

# ── Beyond yfinance: raw Yahoo Finance website functions ──
# These hit Yahoo's public HTTP endpoints directly (no yfinance wrapper, no crumb needed).

def _yahoo_get(url: str, params: dict | None = None, timeout: int = 15) -> dict:
    import requests
    r = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}, timeout=timeout)
    r.raise_for_status()
    return r.json() if "json" in (r.headers.get("content-type") or "") else {"_raw": r.text[:8000]}


def do_trending(args):
    region = (args.region or "US").strip().upper()
    count = int(args.count or 20)
    if count < 1 or count > 50:
        _err("count must be 1..50", code=1)
    use_quotes = not args.symbols_only
    try:
        j = _yahoo_get(f"https://query2.finance.yahoo.com/v1/finance/trending/{region}", {"count": str(count), "useQuotes": str(use_quotes).lower()})
        result = (j.get("finance") or {}).get("result") or []
        if not result:
            _err(f"no trending data for region {region}", region=region)
        quotes = result[0].get("quotes") or []
        if use_quotes:
            rows = [_j(q) for q in quotes[:count]]
        else:
            rows = [{"symbol": q.get("symbol")} for q in quotes[:count] if q.get("symbol")]
        _ok({"region": region, "count": len(rows), "rows": rows, "hasTrendingScore": any("trendingScore" in r for r in rows)}, region=region)
    except SystemExit:
        raise
    except Exception as e:
        _err(f"trending failed for {region}: {e}", region=region)


def do_chart(args):
    sym = args.symbol.strip().upper()
    if not sym:
        _err("symbol required", code=1)
    period = (args.period or "1mo").strip()
    interval = (args.interval or "1d").strip()
    try:
        j = _yahoo_get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", {"range": period, "interval": interval, "includePrePost": "false"})
        result = (j.get("chart") or {}).get("result") or []
        if not result:
            err = (j.get("chart") or {}).get("error") or {}
            _err(err.get("description") or f"no chart data for {sym}", symbol=sym)
        r0 = result[0]
        meta = r0.get("meta") or {}
        ts = r0.get("timestamp") or []
        ind = (r0.get("indicators") or {}).get("quote") or [{}]
        q = ind[0] if ind else {}
        # zip into rows
        import datetime as _dt
        rows = []
        for i, t in enumerate(ts):
            try:
                dt = _dt.datetime.fromtimestamp(t, tz=_dt.timezone.utc).isoformat()
            except Exception:
                dt = str(t)
            rows.append(_j({
                "date": dt,
                "open": (q.get("open") or [None])[i] if i < len(q.get("open") or []) else None,
                "high": (q.get("high") or [None])[i] if i < len(q.get("high") or []) else None,
                "low": (q.get("low") or [None])[i] if i < len(q.get("low") or []) else None,
                "close": (q.get("close") or [None])[i] if i < len(q.get("close") or []) else None,
                "volume": (q.get("volume") or [None])[i] if i < len(q.get("volume") or []) else None,
            }))
        _ok({"symbol": sym, "period": period, "interval": interval, "meta": _j({k: meta[k] for k in ("currency","exchangeName","fullExchangeName","instrumentType","regularMarketPrice","chartPreviousClose","fiftyTwoWeekHigh","fiftyTwoWeekLow","currentTradingPeriod") if k in meta}), "n": len(rows), "rows": rows}, symbol=sym)
    except SystemExit:
        raise
    except Exception as e:
        _err(f"chart failed for {sym}: {e}", symbol=sym)


def do_ysearch(args):
    q = (args.query or "").strip()
    if not q:
        _err("query required", code=1)
    qc = int(args.quotes or 10)
    nc = int(args.news or 2)
    try:
        j = _yahoo_get("https://query2.finance.yahoo.com/v1/finance/search", {"q": q, "quotesCount": str(qc), "newsCount": str(nc), "enableFuzzyQuery": "false"})
        quotes = j.get("quotes") or []
        news = j.get("news") or []
        rows = [_j({k: qu[k] for k in ("symbol","shortname","longname","exchange","quoteType","typeDisp","sector","industry","exchDisp","score") if k in qu}) for qu in quotes[:qc]]
        nrows = []
        for n in news[:nc]:
            nrows.append(_news_item(
                title=n.get("title"),
                url=n.get("link") or n.get("clickThroughUrl", ""),
                publisher=n.get("publisher"),
                published=n.get("providerPublishTime"),
                nid=n.get("uuid"),
                kind=n.get("type"),
            ))
        out: dict = {"query": q, "quotes": rows, "n_quotes": len(rows)}
        if nrows:
            out["news"] = nrows
            out["n_news"] = len(nrows)
        if not rows and not nrows:
            _err(f"no results for '{q}'", query=q)
        _ok(out, query=q)
    except SystemExit:
        raise
    except Exception as e:
        _err(f"ysearch failed for '{q}': {e}", query=q)


def do_web_news(args):
    topic = (args.topic or "").strip().strip("/")
    if not topic:
        _err("topic required (e.g. stock-market-news, earnings, ai)", code=1)
    # Normalize: allow with or without 'topic/' prefix
    if topic.startswith("topic/"):
        topic = topic[len("topic/"):]
    url = f"https://finance.yahoo.com/topic/{topic}/"
    try:
        # keyless scrape via requests (web-local provider also handles web_extract elsewhere)
        # Try local provider first
        from pathlib import Path as _P
        import importlib.util as _ilu
        local_provider = _P.home() / ".hermes" / "plugins" / "web-local" / "web_local_provider.py"
        if local_provider.exists() and _ilu.spec_from_file_location("web_local_provider", str(local_provider)):
            # Use requests + readability-style extract inline (avoid importing plugin machinery)
            pass
        import requests as _rq
        from html import unescape as _ue
        r = _rq.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code == 404:
            _err(f"topic not found: {topic} (tried {url}); try: stock-market-news, latest-news, earnings, economy, personal-finance, crypto", query=topic)
        r.raise_for_status()
        html = r.text
        # Lightweight extract: find article links + titles from Yahoo topic pages
        import re as _re
        items = []
        # Yahoo topic pages render cards with href="/markets/article/..." etc + titles nearby
        for m in _re.finditer(r'href="(/(?:markets|economy|technology|personal-finance|real-estate|media-advertising)/[^"]+)"[^>]*>.*? title="([^"]+)"|href="(/(?:markets|economy|technology)[^"]+)"', html, _re.DOTALL):
            href = m.group(1) or m.group(3)
            title = (m.group(2) or "").strip()
            if href and title and len(title) > 12:
                items.append({"title": _ue(title)[:220], "url": f"https://finance.yahoo.com{href}"})
            if len(items) >= (args.limit or 20):
                break
        # Fallback: grab any finance.yahoo.com article hrefs if regex above missed
        if len(items) < 3:
            for href in _re.findall(r'href="(https://finance\.yahoo\.com/[^"]+)"', html):
                if "/article/" in href or "/articles/" in href or "/live/" in href:
                    if not any(x["url"] == href for x in items):
                        items.append({"title": href.split("/")[-1].replace("-", " ")[:120], "url": href})
                if len(items) >= (args.limit or 20):
                    break
        _ok({"topic": topic, "url": url, "n": len(items), "rows": [_news_item(title=i["title"], url=i["url"]) for i in items[: args.limit or 20]]}, query=topic)
    except SystemExit:
        raise
    except Exception as e:
        _err(f"web-news failed for topic '{topic}': {e}", query=topic)


def do_web_article(args):
    url = (args.url or args.query or "").strip()
    if not url:
        _err("url required (Yahoo Finance article URL)", code=1)
    if not url.startswith("http"):
        url = "https://finance.yahoo.com" + ("/" + url.lstrip("/"))
    try:
        import requests as _rq
        from html import unescape as _ue
        import re as _re
        r = _rq.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        html = r.text
        # Extract <title> and article body
        title = ""
        m = _re.search(r"<title[^>]*>(.*?)</title>", html, _re.DOTALL | _re.IGNORECASE)
        if m:
            title = _ue(_re.sub(r"<[^>]+>", "", m.group(1))).strip()[:300]
        # Yahoo articles use <p> tags or JSON-LD
        paras = _re.findall(r"<p[^>]*>(.*?)</p>", html, _re.DOTALL)
        text_parts = []
        for p in paras:
            t = _ue(_re.sub(r"<[^>]+>", "", p)).strip()
            if len(t) > 40 and "cookie" not in t.lower()[:30]:
                text_parts.append(t)
            if len(" ".join(text_parts)) > 12000:
                break
        body = "\n\n".join(text_parts[:40])
        # JSON-LD fallback
        if len(body) < 300:
            ld = _re.search(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, _re.DOTALL)
            if ld:
                import json as _json
                try:
                    ldj = _json.loads(ld.group(1))
                    cand = ldj.get("articleBody") or ldj.get("description") or ""
                    if cand and len(cand) > len(body):
                        body = cand[:12000]
                except Exception:
                    pass
        _ok({"url": url, "title": title, "text": body[:12000], "chars": len(body)}, query=url)
    except SystemExit:
        raise
    except Exception as e:
        _err(f"web-article failed for {url}: {e}", query=url)

# ── CLI wiring ──


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="yahoo_finance", description="Yahoo Finance CLI (yfinance backend) — token-efficient, agent-native.")
    sub = p.add_subparsers(dest="cmd", required=True)

    # quote
    sp = sub.add_parser("quote", help="Compact quote (price, cap, multiples)")
    sp.add_argument("symbol", help="Ticker symbol (e.g. AAPL, 0700.HK, BTC-USD)")
    sp.add_argument("--fields", help="Comma-separated raw info keys to return (default: compact preset)")
    sp.set_defaults(func=do_quote)

    # history
    sp = sub.add_parser("history", help="OHLCV history")
    sp.add_argument("symbol")
    sp.add_argument("--period", default="1mo", help="1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max (default 1mo)")
    sp.add_argument("--interval", default="1d", help="1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo (default 1d)")
    sp.add_argument("--no-adjust", action="store_true", help="Disable auto-adjust (splits/dividends)")
    sp.add_argument("--actions", action="store_true", help="Include dividends/splits columns")
    sp.add_argument("--limit", type=int, default=100, help="Max rows inline before spill (default 100)")
    sp.add_argument("--json", action="store_true", help="(deprecated) JSON is always on")
    sp.add_argument("--metadata", action="store_true", help="Include history_metadata (exchange, timezone, firstTradeDate, etc.)")
    sp.set_defaults(func=do_history)

    # info
    sp = sub.add_parser("info", help="Full instrument info (quote+profile+stats)")
    sp.add_argument("symbol")
    sp.add_argument("--section", help="Comma-separated: quote,profile,stats (default: all preview+spill)")
    sp.set_defaults(func=do_info)

    # financials
    sp = sub.add_parser("financials", help="Income / balance / cash statements")
    sp.add_argument("symbol")
    sp.add_argument("--statement", default="income", help="income|balance|cash (default income)")
    sp.add_argument("--period", default="annual", help="annual|quarterly|ttm (default annual)")
    sp.set_defaults(func=do_financials)

    # holders
    sp = sub.add_parser("holders", help="Major / institutional / mutualfund / insider holders")
    sp.add_argument("symbol")
    sp.add_argument("--kind", default="all", help="all|major|institutional|mutualfund|insider")
    sp.set_defaults(func=do_holders)

    # calendar
    sp = sub.add_parser("calendar", help="Earnings calendar / dividend date")
    sp.add_argument("symbol")
    sp.set_defaults(func=do_calendar)

    # earnings
    sp = sub.add_parser("earnings", help="Earnings dates (estimate vs reported)")
    sp.add_argument("symbol")
    sp.add_argument("--limit", type=int, default=8)
    sp.set_defaults(func=do_earnings)

    # dividends
    sp = sub.add_parser("dividends", help="Dividend history")
    sp.add_argument("symbol")
    sp.add_argument("--period", default="max")
    sp.set_defaults(func=do_dividends)

    # splits
    sp = sub.add_parser("splits", help="Stock split history")
    sp.add_argument("symbol")
    sp.set_defaults(func=do_splits)

    # options-expiries
    sp = sub.add_parser("options-expiries", help="List option expiry dates")
    sp.add_argument("symbol")
    sp.set_defaults(func=do_options_expiries)

    # options
    sp = sub.add_parser("options", help="Option chain for an expiry")
    sp.add_argument("symbol")
    sp.add_argument("--expiry", help="YYYY-MM-DD (default: nearest)")
    sp.add_argument("--kind", default="both", help="calls|puts|both")
    sp.add_argument("--limit", type=int, default=30, help="Max rows per side inline")
    sp.set_defaults(func=do_options)

    # recommendations
    sp = sub.add_parser("recommendations", help="Analyst recommendations")
    sp.add_argument("symbol")
    sp.set_defaults(func=do_recommendations)

    # upgrades
    sp = sub.add_parser("upgrades", help="Upgrades / downgrades history")
    sp.add_argument("symbol")
    sp.set_defaults(func=do_upgrades)

    # news
    sp = sub.add_parser("news", help="Recent news")
    sp.add_argument("symbol")
    sp.add_argument("--count", type=int, default=5)
    sp.set_defaults(func=do_news)

    # search
    sp = sub.add_parser("search", help="Search tickers / quotes by keyword")
    sp.add_argument("query", help="Search keyword (e.g. 'Apple', 'TSMC')")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=do_search)

    # screener
    sp = sub.add_parser("screener", help="Predefined Yahoo screener")
    sp.add_argument("name", help="e.g. day_gainers, day_losers, most_actives, growth_technology_stocks, ...")
    sp.add_argument("--limit", type=int, default=25)
    sp.add_argument("--offset", type=int, default=0)
    sp.set_defaults(func=do_screener)

    # screener-custom
    sp = sub.add_parser("screener-custom", help="Custom screener (JSON query body)")
    sp.add_argument("--query", required=True, help="JSON string for screener query body")
    sp.add_argument("--limit", type=int, default=25)
    sp.add_argument("--offset", type=int, default=0)
    sp.set_defaults(func=do_screener_custom)

    # download (bulk)
    sp = sub.add_parser("download", help="Bulk OHLCV download (multi-ticker)")
    sp.add_argument("symbols", help="Comma-separated symbols (e.g. AAPL,MSFT,GOOGL)")
    sp.add_argument("--period", default="1mo")
    sp.add_argument("--interval", default="1d")
    sp.set_defaults(func=do_download)

    # sector
    sp = sub.add_parser("sector", help="Sector overview (top companies / ETFs)")
    sp.add_argument("name", help="e.g. technology, healthcare, financial-services, energy")
    sp.set_defaults(func=do_sector)

    # industry
    sp = sub.add_parser("industry", help="Industry overview (complements sector)")
    sp.add_argument("name", help="e.g. software-infrastructure, semiconductors, banks-diversified")
    sp.set_defaults(func=do_industry)

    # analysis (analyst estimates)
    sp = sub.add_parser("analysis", help="Analyst estimates: price targets, EPS trend/revisions, revenue & growth")
    sp.add_argument("symbol")
    sp.set_defaults(func=do_analysis)

    # esg / sustainability
    sp = sub.add_parser("esg", help="ESG / sustainability scores")
    sp.add_argument("symbol")
    sp.set_defaults(func=do_esg)

    # filings
    sp = sub.add_parser("filings", help="SEC filings (10-K, 10-Q, 8-K, etc.)")
    sp.add_argument("symbol")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=do_filings)

    # funds (ETF / mutual fund holdings)
    sp = sub.add_parser("funds", help="Fund holdings & sector weightings (ETF/mutual fund, e.g. SPY)")
    sp.add_argument("symbol")
    sp.set_defaults(func=do_funds)

    # isin
    sp = sub.add_parser("isin", help="ISIN lookup")
    sp.add_argument("symbol")
    sp.set_defaults(func=do_isin)

    # shares (outstanding history)
    sp = sub.add_parser("shares", help="Shares outstanding history")
    sp.add_argument("symbol")
    sp.add_argument("--start", default="", help="Start date YYYY-MM-DD (default 2020-01-01)")
    sp.add_argument("--end", default="", help="End date YYYY-MM-DD")
    sp.add_argument("--limit", type=int, default=50)
    sp.set_defaults(func=do_shares)

    # market status
    sp = sub.add_parser("market", help="Market open/close status")
    sp.add_argument("name", nargs="?", default="US", help="Market: US, EUROPE, ASIA, RATES, etc. (default US)")
    sp.set_defaults(func=do_market)

    # lookup (quoteType discovery)
    sp = sub.add_parser("lookup", help="Ticker lookup by quoteType (search across stocks/ETFs/indices)")
    sp.add_argument("query", help="Search term")
    sp.add_argument("--kind", default="all", help="all|stock|etf|mutualfund|index|future|currency|cryptocurrency")
    sp.add_argument("--limit", type=int, default=25)
    sp.set_defaults(func=do_lookup)

    # ── Beyond yfinance: raw Yahoo HTTP ──
    sp = sub.add_parser("trending", help="Trending tickers (Yahoo homepage — no auth)")
    sp.add_argument("--region", default="US", help="Region: US, CA, GB, etc. (default US)")
    sp.add_argument("--count", type=int, default=20, help="Count 1..50 (default 20)")
    sp.add_argument("--symbols-only", action="store_true", help="Return symbols only (no quotes)")
    sp.set_defaults(func=do_trending)

    sp = sub.add_parser("chart", help="Raw chart bars via v8 chart endpoint (no crumb)")
    sp.add_argument("symbol", help="Ticker symbol")
    sp.add_argument("--period", default="1mo", help="1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max")
    sp.add_argument("--interval", default="1d", help="1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo")
    sp.set_defaults(func=do_chart)

    sp = sub.add_parser("ysearch", help="Yahoo autocomplete search (fuzzy, scored — richer than yfinance Search)")
    sp.add_argument("query", help="Search term (e.g. 'Apple')")
    sp.add_argument("--quotes", type=int, default=10, help="Quotes count (default 10)")
    sp.add_argument("--news", type=int, default=2, help="News count (default 2)")
    sp.set_defaults(func=do_ysearch)

    sp = sub.add_parser("web-news", help="News by Yahoo topic section (stock-market-news, earnings, ai, etc.)")
    sp.add_argument("topic", help="Topic slug, e.g. stock-market-news, earnings, technology")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=do_web_news)

    sp = sub.add_parser("web-article", help="Article text extract (Yahoo Finance article URL)")
    sp.add_argument("url", help="Full Yahoo Finance article URL (or path)")
    sp.set_defaults(func=do_web_article)

    return p

def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as e:
        _err(f"unhandled: {e}", code=2)

if __name__ == "__main__":
    main()
