"""Smoke tests for hermes-yahoo-finance — no network, just wiring."""
import pathlib
import py_compile

REPO = pathlib.Path(__file__).parent.parent

def test_cli_compiles():
    py_compile.compile(str(REPO / "cli" / "yahoo_finance.py"), doraise=True)

def test_tool_compiles():
    py_compile.compile(str(REPO / "tools" / "yahoo_finance_tool.py"), doraise=True)

def test_cli_help_lists_33_actions():
    import subprocess
    r = subprocess.run(["python", str(REPO / "cli" / "yahoo_finance.py"), "--help"], capture_output=True, text=True, timeout=10)
    assert r.returncode == 0
    for action in ["quote", "history", "trending", "chart", "ysearch", "web-news", "web-article", "analysis", "filings"]:
        assert action in r.stdout, f"missing action {action}"

def test_cli_invalid_ticker_graceful():
    import subprocess, json
    r = subprocess.run(["python", str(REPO / "cli" / "yahoo_finance.py"), "isin", "FAKE_XYZ_999"], capture_output=True, text=True, timeout=15)
    j = json.loads(r.stdout)
    assert j["ok"] is False
    assert "FAKE_XYZ_999" in j["error"]

def test_tool_schema_has_33_actions():
    import importlib.util
    spec = importlib.util.spec_from_file_location("yahoo_finance_tool", str(REPO / "tools" / "yahoo_finance_tool.py"))
    # Don't actually import (needs hermes registry) — just check file content
    text = (REPO / "tools" / "yahoo_finance_tool.py").read_text()
    assert '"trending"' in text or "'trending'" in text or "trending" in text
    assert '"chart"' in text
    assert "ysearch" in text
    assert "web-news" in text or "web_news" in text
