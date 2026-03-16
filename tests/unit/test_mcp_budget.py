"""Tests for budget scope MCP tools - full stack through SDK to config file."""

import asyncio
import json

from bills.mcp.server import mcp


def call(tool_name: str, args: dict = None) -> dict:
    """Invoke MCP tool synchronously, return parsed result."""
    result = asyncio.run(mcp.call_tool(tool_name, args or {}))
    return json.loads(result[0].text)


class TestGetBudgetScope:
    def test_returns_defaults_when_no_config(self, config_dir):
        result = call("get_budget_scope")
        assert result["properties_residence"] is True
        assert result["properties_rental"] is False
        assert result["credit"] is True
        assert result["subscriptions"] is True


class TestUpdateBudgetScope:
    def test_updates_single_field(self, config_dir):
        result = call("update_budget_scope", {"properties_rental": True})
        assert result["success"] is True
        assert result["budget_scope"]["properties_rental"] is True

    def test_updates_multiple_fields(self, config_dir):
        result = call("update_budget_scope", {
            "properties_residence": False,
            "credit": False,
            "subscriptions": False,
        })
        assert result["success"] is True
        scope = result["budget_scope"]
        assert scope["properties_residence"] is False
        assert scope["credit"] is False
        assert scope["subscriptions"] is False

    def test_preserves_unmodified_fields(self, config_dir):
        call("update_budget_scope", {"properties_rental": True, "credit": False})
        call("update_budget_scope", {"subscriptions": False})

        result = call("get_budget_scope")
        assert result["properties_rental"] is True  # preserved
        assert result["credit"] is False  # preserved
        assert result["subscriptions"] is False  # updated
        assert result["properties_residence"] is True  # default preserved
