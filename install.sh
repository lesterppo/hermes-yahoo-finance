#!/usr/bin/env bash
# install.sh — install the Hermes yahoo_finance tool + skill.
# Idempotent. Copies:
#   tools/yahoo_finance_tool.py -> <hermes-agent>/tools/
#   cli/yahoo_finance.py        -> ~/.hermes/scripts/yahoo-finance/
#   skills/yahoo-finance/       -> ~/.hermes/skills/finance/yahoo-finance/
#
# It does NOT modify core files (toolsets.py / tools_config.py) automatically —
# those edits are documented in README.md / AGENTS.md and applied by the user
# (or a Hermes agent) because they touch the agent core. The tool self-registers
# via the registry import, but it only becomes exposed to the model after being
# added to a toolset.
#
# Usage:
#   ./install.sh [--hermes-agent /path/to/hermes-agent]
#
# Privacy: this repo contains NO secrets, API keys, or personal paths.

set -euo pipefail

HERMES_AGENT="${1:-}"
if [[ -z "$HERMES_AGENT" ]]; then
  for p in \
    "$HOME/.hermes/hermes-agent" \
    "$(pwd)/hermes-agent" \
    "/opt/hermes-agent"; do
    if [[ -f "$p/tools/registry.py" ]]; then HERMES_AGENT="$p"; break; fi
  done
fi

if [[ -z "$HERMES_AGENT" || ! -f "$HERMES_AGENT/tools/registry.py" ]]; then
  echo "ERROR: could not locate hermes-agent (need tools/registry.py)." >&2
  echo "Pass it explicitly:  ./install.sh /path/to/hermes-agent" >&2
  exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$HOME/.hermes/skills/finance/yahoo-finance"
CLI_DIR="$HOME/.hermes/scripts/yahoo-finance"

echo "==> Hermes agent: $HERMES_AGENT"

# 1) Tool
cp "$SRC/tools/yahoo_finance_tool.py" "$HERMES_AGENT/tools/"
echo "    copied tool -> $HERMES_AGENT/tools/yahoo_finance_tool.py"

# 2) CLI
mkdir -p "$CLI_DIR"
cp "$SRC/cli/yahoo_finance.py" "$CLI_DIR/"
chmod +x "$CLI_DIR/yahoo_finance.py"
# Also link to ~/.local/bin for convenience
if [[ -d "$HOME/.local/bin" ]]; then
  ln -sf "$CLI_DIR/yahoo_finance.py" "$HOME/.local/bin/yahoo_finance"
  echo "    linked CLI -> ~/.local/bin/yahoo_finance"
fi
echo "    copied CLI  -> $CLI_DIR/yahoo_finance.py"

# 3) Skill
mkdir -p "$SKILL_DIR/references"
cp "$SRC/skills/yahoo-finance/SKILL.md" "$SKILL_DIR/"
cp "$SRC/skills/yahoo-finance/references/"*.md "$SKILL_DIR/references/" 2>/dev/null || true
echo "    copied skill -> $SKILL_DIR/"

# 4) Verify
( cd "$HERMES_AGENT" && python3 -c "import tools.yahoo_finance_tool as m; assert m.YAHOO_FINANCE_SCHEMA['name']=='yahoo_finance'; print('    import OK, actions =', len(m._ACTION_MAP))" ) \
  || { echo "ERROR: tool failed to import in $HERMES_AGENT" >&2; exit 1; }

echo ""
echo "Done. Wire into a toolset (README.md): add \"yahoo_finance\" to _HERMES_CORE_TOOLS in toolsets.py"
echo "  and to CONFIGURABLE_TOOLSETS in hermes_cli/tools_config.py, then restart Hermes."
echo "Standalone: python $CLI_DIR/yahoo_finance.py quote AAPL"
