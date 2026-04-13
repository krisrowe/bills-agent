"""Integration tests that launch Claude Code with the bills plugin.

Each test runs claude --bare -p with a prompt and verifies the output.
Uses a stub Monarch MCP server (stub_monarch_mcp.py) so no real financial
data is accessed.

Run:
    export ANTHROPIC_API_KEY=<your key>
    pytest tests/claude/
    make test-claude
"""

import os
import subprocess
import sys

import pytest

from .conftest import requires_claude


def _build_allowed_tools():
    """Build the allowed tools list using the same env var as the launcher."""
    monarch = os.environ.get("BILLS_MONARCH_MCP", "*")
    return [
        # bills-mcp (registered as "bills" under --bare via --mcp-config)
        "mcp__bills__list_*",
        "mcp__bills__get_*",
        "mcp__bills__show_*",
        "mcp__bills__validate_*",
        "mcp__bills__build_bill_inventory",
        "mcp__bills__get_inventory_section",
        # stub monarch
        f"mcp__{monarch}__list_recurring",
        f"mcp__{monarch}__list_accounts",
        f"mcp__{monarch}__list_categories",
        f"mcp__{monarch}__list_transactions",
    ]


def _run_claude(plugin_dir, mcp_config, prompt, allowed_tools=None, timeout=120):
    """Run claude --bare -p with the bills plugin and stub monarch."""
    cmd = [
        "claude",
        "--bare",
        "--plugin-dir", plugin_dir,
        "--mcp-config", mcp_config,
        "-p", prompt,
    ]
    for tool in (allowed_tools or []):
        cmd.extend(["--allowedTools", tool])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result


PROMPT = "List my credit card accounts with a balance >= $500. Be brief."


@requires_claude
class TestToolAllowlist:
    """Verify that --allowedTools patterns work with the bills plugin."""

    def test_with_allowed_tools(
        self, plugin_dir, mcp_config, bills_config
    ):
        """Pre-approved tools execute and return account data."""
        result = _run_claude(
            plugin_dir, mcp_config, PROMPT,
            allowed_tools=_build_allowed_tools(),
        )
        assert result.returncode == 0, f"claude failed: {result.stderr}"
        output = result.stdout.lower()
        assert "4567" in output or "test rewards" in output or "1250" in output, (
            f"Expected account data in output, got:\n{result.stdout}"
        )

    def test_without_allowed_tools(
        self, plugin_dir, mcp_config, bills_config
    ):
        """Without allowlist, tools are blocked and agent completes without data."""
        result = _run_claude(
            plugin_dir, mcp_config, PROMPT,
            allowed_tools=[],
        )
        assert result.returncode == 0, f"claude failed: {result.stderr}"
        output = result.stdout.lower()
        # Should NOT contain account data since tools weren't approved
        assert "4567" not in output and "1250" not in output, (
            f"Expected no account data without allowed tools, got:\n{result.stdout}"
        )
