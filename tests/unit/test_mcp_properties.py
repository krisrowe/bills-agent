"""Tests for property MCP tools - full stack through SDK to config file."""

import asyncio
import json

from bills.mcp.server import mcp


def call(tool_name: str, args: dict = None) -> dict:
    """Invoke MCP tool synchronously, return parsed result."""
    result = asyncio.run(mcp.call_tool(tool_name, args or {}))
    return json.loads(result[0].text)


class TestListProperties:
    def test_returns_empty_initially(self, config_dir):
        result = call("list_properties")
        assert result["count"] == 0
        assert result["properties"] == []

    def test_returns_properties_with_bills(self, config_dir):
        call("register_property_bill", {"property_name": "Home", "bill_name": "Electric", "vendor": "Power Co"})
        call("register_property_bill", {"property_name": "Home", "bill_name": "Water", "vendor": "City"})
        call("register_property_bill", {"property_name": "Rental", "bill_name": "Trash", "vendor": "Waste Co"})

        result = call("list_properties")
        assert result["count"] == 2

        home = next(p for p in result["properties"] if p["name"] == "Home")
        assert len(home["bills"]) == 2


class TestListPropertyBills:
    def test_returns_bills_for_property(self, config_dir):
        call("register_property_bill", {"property_name": "Home", "bill_name": "Electric", "vendor": "Power"})
        call("register_property_bill", {"property_name": "Home", "bill_name": "Water", "vendor": "City"})
        call("register_property_bill", {"property_name": "Home", "bill_name": "Internet", "vendor": "ISP"})

        result = call("list_property_bills", {"property_name": "Home"})
        assert result["count"] == 3
        assert result["property"] == "Home"

    def test_returns_empty_for_unknown_property(self, config_dir):
        result = call("list_property_bills", {"property_name": "Unknown"})
        assert result["count"] == 0
        assert "error" in result

    def test_case_insensitive_lookup(self, config_dir):
        call("register_property_bill", {"property_name": "Beach House", "bill_name": "Electric", "vendor": "Power"})
        result = call("list_property_bills", {"property_name": "BEACH HOUSE"})
        assert result["count"] == 1


class TestRegisterPropertyBill:
    def test_creates_property_when_missing(self, config_dir):
        result = call("register_property_bill", {
            "property_name": "New Property",
            "bill_name": "Electric",
            "vendor": "Power Co",
        })
        assert result["success"] is True
        assert result["bill"]["name"] == "Electric"

        props = call("list_properties")
        assert props["count"] == 1
        assert props["properties"][0]["name"] == "New Property"

    def test_adds_bill_to_existing_property(self, config_dir):
        call("register_property_bill", {"property_name": "Home", "bill_name": "Electric", "vendor": "Power"})
        call("register_property_bill", {"property_name": "Home", "bill_name": "Water", "vendor": "City"})

        result = call("list_properties")
        assert result["count"] == 1
        assert len(result["properties"][0]["bills"]) == 2

    def test_registers_with_all_fields(self, config_dir):
        result = call("register_property_bill", {
            "property_name": "Rental",
            "bill_name": "Mortgage",
            "vendor": "Lender Corp",
            "due_day": 1,
            "amount": 1500.00,
            "payment_method": "auto_draft",
            "funding_account": "9999",
            "type": "rental",
            "managed_by": "spouse",
            "notes": "Escrow included",
        })
        assert result["success"] is True
        bill = result["bill"]
        assert bill["due_day"] == 1
        assert bill["amount"] == 1500.00
        assert bill["payment_method"] == "auto_draft"
        assert bill["managed_by"] == "spouse"
        assert bill["notes"] == "Escrow included"

    def test_rejects_duplicate_bill_name(self, config_dir):
        call("register_property_bill", {"property_name": "Home", "bill_name": "Electric", "vendor": "Power"})
        result = call("register_property_bill", {"property_name": "Home", "bill_name": "Electric", "vendor": "Other"})
        assert result["success"] is False
        assert "already exists" in result["error"]

    def test_property_lookup_case_insensitive(self, config_dir):
        call("register_property_bill", {"property_name": "Primary Residence", "bill_name": "Electric", "vendor": "Power"})
        result = call("register_property_bill", {"property_name": "primary residence", "bill_name": "Water", "vendor": "City"})
        assert result["success"] is True

        props = call("list_properties")
        assert props["count"] == 1
        assert len(props["properties"][0]["bills"]) == 2


class TestUpdateProperty:
    def test_updates_address(self, config_dir):
        call("register_property_bill", {"property_name": "Home", "bill_name": "Electric", "vendor": "Power"})
        result = call("update_property", {"name": "Home", "address": "123 Main St"})
        assert result["success"] is True
        assert result["property"]["address"] == "123 Main St"

    def test_updates_type(self, config_dir):
        call("register_property_bill", {"property_name": "Rental", "bill_name": "Mortgage", "vendor": "Bank"})
        result = call("update_property", {"name": "Rental", "type": "rental"})
        assert result["success"] is True
        assert result["property"]["type"] == "rental"

    def test_updates_multiple_fields(self, config_dir):
        call("register_property_bill", {"property_name": "Beach", "bill_name": "Water", "vendor": "City"})
        result = call("update_property", {
            "name": "Beach",
            "address": "456 Ocean Dr",
            "tax_id": "TX-12345",
            "notes": "Vacation home",
        })
        assert result["success"] is True
        prop = result["property"]
        assert prop["address"] == "456 Ocean Dr"
        assert prop["tax_id"] == "TX-12345"
        assert prop["notes"] == "Vacation home"

    def test_fails_for_unknown_property(self, config_dir):
        result = call("update_property", {"name": "Unknown", "address": "123 Fake St"})
        assert result["success"] is False
        assert "No property" in result["error"]

    def test_case_insensitive_lookup(self, config_dir):
        call("register_property_bill", {"property_name": "Main House", "bill_name": "Mortgage", "vendor": "Bank"})
        result = call("update_property", {"name": "MAIN HOUSE", "address": "123 Main St"})
        assert result["success"] is True
