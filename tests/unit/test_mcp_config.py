"""Tests for config MCP tools - validation and path info."""

import asyncio
import json

from bills.mcp.server import mcp


def call(tool_name: str, args: dict = None) -> dict:
    """Invoke MCP tool synchronously, return parsed result."""
    result = asyncio.run(mcp.call_tool(tool_name, args or {}))
    return json.loads(result[0].text)


class TestValidateConfig:
    def test_reports_missing_config_file(self, config_dir):
        result = call("validate_config")
        assert result["valid"] is False
        assert "not found" in result["error"]

    def test_reports_valid_after_registration(self, config_dir):
        call("register_credit_account", {"name": "Card", "issuer": "Bank"})

        result = call("validate_config")
        assert result["valid"] is True
        assert "config_path" in result
        assert result["summary"]["credit_accounts"] == 1

    def test_counts_promo_accounts_correctly(self, config_dir):
        call("register_credit_account", {"name": "No Promo", "issuer": "Bank", "last4": "1111"})
        call("register_credit_account", {"name": "Has Promo", "issuer": "Bank", "last4": "2222"})
        call("add_promo", {"account_last4": "2222", "balance": 500.00})
        call("add_promo", {"account_last4": "2222", "balance": 300.00})

        result = call("validate_config")
        assert result["summary"]["credit_accounts"] == 2
        assert result["summary"]["accounts_with_promo"] == 1
        assert result["summary"]["total_promo_plans"] == 2


class TestShowConfigPath:
    def test_returns_path_info(self, config_dir):
        result = call("show_config_path")
        assert "config_path" in result
        assert "bills" in result["config_path"]
        assert "config.yaml" in result["config_path"]

    def test_reports_exists_false_initially(self, config_dir):
        result = call("show_config_path")
        assert result["exists"] is False

    def test_reports_exists_true_after_write(self, config_dir):
        call("register_credit_account", {"name": "Card", "issuer": "Bank"})
        result = call("show_config_path")
        assert result["exists"] is True
