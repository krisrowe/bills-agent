"""Configuration for Claude Code integration tests.

These tests launch Claude Code with --bare and -p to verify that the bills
plugin loads correctly, MCP tools register, and --allowedTools patterns work.

Requirements:
- Claude Code installed locally (claude on PATH)
- ANTHROPIC_API_KEY set (--bare disables OAuth/keychain)

Each test makes a real API call to Anthropic. These are excluded from default
pytest runs (testpaths = tests/unit in pytest.ini). Run explicitly:
    pytest tests/claude/
    make test-claude

Limitations:
- Plugin PostToolUse hooks do NOT fire under --bare. Hook behavior (Monarch
  response caching, context compression) is not tested here.
- Tests verify the agent's text output, which is non-deterministic. Assertions
  check for reasonable signals (tool was called, data appeared) rather than
  exact strings.
"""

import json
import os
import shutil
import sys
from importlib.resources import files
from pathlib import Path

import pytest

# Set the monarch MCP server name for allowedTools patterns.
# Under --bare, globs don't work, so the launcher's default "*" won't match.
# The stub server is registered as "monarch" in the test MCP config.
os.environ.setdefault("BILLS_MONARCH_MCP", "monarch")

_CLAUDE_ON_PATH = shutil.which("claude") is not None
_HAS_API_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))


def _skip_reason():
    if not _CLAUDE_ON_PATH:
        return "claude not found on PATH"
    if not _HAS_API_KEY:
        return "ANTHROPIC_API_KEY not set (required for --bare mode)"
    return None


_reason = _skip_reason()
requires_claude = pytest.mark.skipif(_reason is not None, reason=_reason or "")


@pytest.fixture
def plugin_dir():
    """Path to the bills plugin directory."""
    return str(files("bills") / ".." / "claude" / "plugin")


@pytest.fixture
def mcp_config(tmp_path):
    """Create an MCP config with bills-mcp and stub monarch server.

    --bare skips the plugin's .mcp.json, so we must register bills-mcp
    explicitly alongside the stub monarch server.
    """
    stub_server = Path(__file__).parent / "stub_monarch_mcp.py"
    config = {
        "mcpServers": {
            "bills": {
                "command": "bills-mcp",
            },
            "monarch": {
                "command": sys.executable,
                "args": [str(stub_server)],
            },
        }
    }
    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps(config))
    return str(config_path)


@pytest.fixture
def bills_config(tmp_path, monkeypatch):
    """Seed a bills config with a test credit account."""
    config_dir = tmp_path / "config" / "bills"
    config_dir.mkdir(parents=True)
    config = {
        "credit_accounts": [
            {
                "last4": "4567",
                "name": "Test Rewards Card",
                "issuer": "Test Bank",
                "due_day": 15,
                "payment_method": "auto_pay",
            }
        ],
        "properties": [],
        "funding_accounts": [],
        "bill_filters": {"categories": ["*Mortgage*", "*Insurance*"]},
        "ignored_merchants": [],
    }
    import yaml
    (config_dir / "config.yaml").write_text(yaml.dump(config))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return config_dir
