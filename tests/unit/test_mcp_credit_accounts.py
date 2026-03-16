"""Tests for credit account MCP tools - full stack through SDK to config file."""

import asyncio
import json

from bills.mcp.server import mcp


def call(tool_name: str, args: dict = None) -> dict:
    """Invoke MCP tool synchronously, return parsed result."""
    result = asyncio.run(mcp.call_tool(tool_name, args or {}))
    return json.loads(result[0].text)


class TestListCreditAccounts:
    def test_returns_empty_list_initially(self, config_dir):
        result = call("list_credit_accounts")
        assert result["count"] == 0
        assert result["credit_accounts"] == []

    def test_returns_registered_accounts(self, config_dir):
        call("register_credit_account", {"name": "Card A", "issuer": "Bank A"})
        call("register_credit_account", {"name": "Card B", "issuer": "Bank B"})

        result = call("list_credit_accounts")
        assert result["count"] == 2
        names = [a["name"] for a in result["credit_accounts"]]
        assert "Card A" in names
        assert "Card B" in names


class TestRegisterCreditAccount:
    def test_registers_minimal_account(self, config_dir):
        result = call("register_credit_account", {
            "name": "Test Card",
            "issuer": "Test Bank",
        })
        assert result["success"] is True
        assert result["credit_account"]["name"] == "Test Card"
        assert result["credit_account"]["issuer"] == "Test Bank"

    def test_registers_with_all_fields(self, config_dir):
        result = call("register_credit_account", {
            "name": "Sapphire",
            "issuer": "Chase",
            "last4": "4567",
            "due_day": 15,
            "payment_method": "auto_pay_full",
            "funding_account": "1234",
            "vendor": False,
            "notes": "Primary travel card",
        })
        assert result["success"] is True
        acct = result["credit_account"]
        assert acct["last4"] == "4567"
        assert acct["due_day"] == 15
        assert acct["payment_method"] == "auto_pay_full"
        assert acct["notes"] == "Primary travel card"

    def test_rejects_duplicate_last4(self, config_dir):
        call("register_credit_account", {"name": "Card 1", "issuer": "Bank", "last4": "9999"})
        result = call("register_credit_account", {"name": "Card 2", "issuer": "Bank", "last4": "9999"})
        assert result["success"] is False
        assert "already exists" in result["error"]


class TestGetCreditAccount:
    def test_finds_account_by_last4(self, config_dir):
        call("register_credit_account", {"name": "Target", "issuer": "TD", "last4": "5555"})
        result = call("get_credit_account", {"last4": "5555"})
        assert result["found"] is True
        assert result["credit_account"]["name"] == "Target"

    def test_returns_not_found_for_unknown(self, config_dir):
        result = call("get_credit_account", {"last4": "0000"})
        assert result["found"] is False


class TestUpdateCreditAccount:
    def test_updates_single_field(self, config_dir):
        call("register_credit_account", {"name": "Card", "issuer": "Bank", "last4": "1111"})
        result = call("update_credit_account", {"last4": "1111", "due_day": 20})
        assert result["success"] is True
        assert result["credit_account"]["due_day"] == 20

    def test_updates_multiple_fields(self, config_dir):
        call("register_credit_account", {"name": "Card", "issuer": "Bank", "last4": "2222"})
        result = call("update_credit_account", {
            "last4": "2222",
            "name": "Updated Card",
            "payment_method": "auto_pay_min",
            "notes": "Updated notes",
        })
        assert result["success"] is True
        assert result["credit_account"]["name"] == "Updated Card"
        assert result["credit_account"]["payment_method"] == "auto_pay_min"

    def test_preserves_unmodified_fields(self, config_dir):
        call("register_credit_account", {
            "name": "Card",
            "issuer": "Original Bank",
            "last4": "3333",
            "due_day": 10,
        })
        call("update_credit_account", {"last4": "3333", "notes": "Added notes"})

        result = call("get_credit_account", {"last4": "3333"})
        assert result["credit_account"]["issuer"] == "Original Bank"
        assert result["credit_account"]["due_day"] == 10

    def test_fails_for_unknown_account(self, config_dir):
        result = call("update_credit_account", {"last4": "9999", "name": "New"})
        assert result["success"] is False
        assert "No account" in result["error"]


class TestPromoManagement:
    def test_add_promo_to_account(self, config_dir):
        call("register_credit_account", {"name": "Best Buy", "issuer": "Synchrony", "last4": "7777", "vendor": True})
        result = call("add_promo", {
            "account_last4": "7777",
            "balance": 1200.00,
            "description": "TV purchase",
            "expires": "2026-12-15",
            "updated": "2026-01-27",
        })
        assert result["success"] is True
        assert result["promo"]["balance"] == 1200.00
        assert result["promo"]["description"] == "TV purchase"

    def test_add_multiple_promos_same_account(self, config_dir):
        call("register_credit_account", {"name": "Citi", "issuer": "Citi", "last4": "8888"})
        call("add_promo", {"account_last4": "8888", "balance": 500.00, "description": "Plan 1"})
        call("add_promo", {"account_last4": "8888", "balance": 750.00, "description": "Plan 2"})
        call("add_promo", {"account_last4": "8888", "balance": 1000.00, "description": "Plan 3"})

        result = call("get_credit_account", {"last4": "8888"})
        promos = result["credit_account"]["promos"]
        assert len(promos) == 3
        assert promos[0]["description"] == "Plan 1"
        assert promos[2]["description"] == "Plan 3"

    def test_add_promo_fails_unknown_account(self, config_dir):
        result = call("add_promo", {"account_last4": "0000", "balance": 100.00})
        assert result["success"] is False
        assert "No account" in result["error"]

    def test_update_promo_balance(self, config_dir):
        call("register_credit_account", {"name": "Store", "issuer": "Sync", "last4": "4444"})
        call("add_promo", {"account_last4": "4444", "balance": 1000.00, "description": "Original"})

        result = call("update_promo", {
            "account_last4": "4444",
            "promo_index": 0,
            "balance": 800.00,
            "updated": "2026-01-27",
        })
        assert result["success"] is True
        assert result["promo"]["balance"] == 800.00
        assert result["promo"]["updated"] == "2026-01-27"

    def test_update_promo_preserves_other_fields(self, config_dir):
        call("register_credit_account", {"name": "Store", "issuer": "Sync", "last4": "5544"})
        call("add_promo", {
            "account_last4": "5544",
            "balance": 1000.00,
            "description": "TV",
            "expires": "2026-06-01",
            "payment_amount": 100.00,
        })
        call("update_promo", {"account_last4": "5544", "promo_index": 0, "balance": 900.00})

        result = call("get_credit_account", {"last4": "5544"})
        promo = result["credit_account"]["promos"][0]
        assert promo["description"] == "TV"
        assert promo["expires"] == "2026-06-01"
        assert promo["payment_amount"] == 100.00

    def test_update_promo_fails_invalid_index(self, config_dir):
        call("register_credit_account", {"name": "Store", "issuer": "Sync", "last4": "6644"})
        call("add_promo", {"account_last4": "6644", "balance": 500.00})

        result = call("update_promo", {"account_last4": "6644", "promo_index": 5, "balance": 400.00})
        assert result["success"] is False
        assert "out of range" in result["error"]

    def test_remove_promo(self, config_dir):
        call("register_credit_account", {"name": "Store", "issuer": "Sync", "last4": "7744"})
        call("add_promo", {"account_last4": "7744", "balance": 500.00, "description": "First"})
        call("add_promo", {"account_last4": "7744", "balance": 600.00, "description": "Second"})

        result = call("remove_promo", {"account_last4": "7744", "promo_index": 0})
        assert result["success"] is True
        assert "First" in result["message"]

        acct_result = call("get_credit_account", {"last4": "7744"})
        promos = acct_result["credit_account"]["promos"]
        assert len(promos) == 1
        assert promos[0]["description"] == "Second"

    def test_remove_promo_fails_invalid_index(self, config_dir):
        call("register_credit_account", {"name": "Store", "issuer": "Sync", "last4": "8844"})
        result = call("remove_promo", {"account_last4": "8844", "promo_index": 0})
        assert result["success"] is False
        assert "out of range" in result["message"]


class TestListPromoAccounts:
    def test_returns_empty_when_no_promos(self, config_dir):
        call("register_credit_account", {"name": "Card", "issuer": "Bank", "last4": "1111"})
        result = call("list_promo_accounts")
        assert result["count"] == 0

    def test_returns_only_accounts_with_promos(self, config_dir):
        call("register_credit_account", {"name": "No Promo", "issuer": "Bank", "last4": "1111"})
        call("register_credit_account", {"name": "Has Promo", "issuer": "Bank", "last4": "2222"})
        call("register_credit_account", {"name": "Also Has", "issuer": "Bank", "last4": "3333"})

        call("add_promo", {"account_last4": "2222", "balance": 500.00})
        call("add_promo", {"account_last4": "3333", "balance": 750.00})

        result = call("list_promo_accounts")
        assert result["count"] == 2
        last4s = [a["last4"] for a in result["promo_accounts"]]
        assert "1111" not in last4s
        assert "2222" in last4s
        assert "3333" in last4s
