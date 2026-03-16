"""Tests for funding account MCP tools - full stack through SDK to config file."""

import asyncio
import json

from bills.mcp.server import mcp


def call(tool_name: str, args: dict = None) -> dict:
    """Invoke MCP tool synchronously, return parsed result."""
    result = asyncio.run(mcp.call_tool(tool_name, args or {}))
    return json.loads(result[0].text)


class TestListFundingAccounts:
    def test_returns_empty_initially(self, config_dir):
        result = call("list_funding_accounts")
        assert result["count"] == 0
        assert result["funding_accounts"] == []

    def test_returns_registered_accounts(self, config_dir):
        call("register_funding_account", {"name": "Checking", "last4": "1111", "bank": "Chase"})
        call("register_funding_account", {"name": "Savings", "last4": "2222", "bank": "Ally"})

        result = call("list_funding_accounts")
        assert result["count"] == 2
        names = [a["name"] for a in result["funding_accounts"]]
        assert "Checking" in names
        assert "Savings" in names


class TestRegisterFundingAccount:
    def test_registers_with_required_fields(self, config_dir):
        result = call("register_funding_account", {
            "name": "Chase Checking",
            "last4": "9999",
            "bank": "Chase",
        })
        assert result["success"] is True
        assert result["funding_account"]["name"] == "Chase Checking"
        assert result["funding_account"]["bank"] == "Chase"

    def test_registers_with_optional_fields(self, config_dir):
        result = call("register_funding_account", {
            "name": "Primary",
            "last4": "8888",
            "bank": "Chase",
            "monarch_id": "mon_12345",
        })
        assert result["success"] is True
        assert result["funding_account"]["monarch_id"] == "mon_12345"

    def test_rejects_duplicate_last4(self, config_dir):
        call("register_funding_account", {"name": "Account 1", "last4": "1234", "bank": "Bank"})
        result = call("register_funding_account", {"name": "Account 2", "last4": "1234", "bank": "Bank"})
        assert result["success"] is False
        assert "already exists" in result["error"]
