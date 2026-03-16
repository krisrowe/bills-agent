"""Tests for bill filter management."""

from bills.sdk.common.config import BillFilterConfig, load_config, save_config, BillsConfig
from bills.sdk.common.filters import (
    add_bill_filter,
    get_bill_filters,
    matches_filter,
    remove_bill_filter,
    set_bill_filters,
)


class TestMatchesFilter:
    def test_exact_match(self):
        filters = BillFilterConfig(categories=["Water"])
        assert matches_filter("Water", filters) is True

    def test_no_match(self):
        filters = BillFilterConfig(categories=["Water"])
        assert matches_filter("Shopping", filters) is False

    def test_glob_contains(self):
        filters = BillFilterConfig(categories=["*Mortgage*"])
        assert matches_filter("Rental Property Mortgage", filters) is True
        assert matches_filter("Mortgage", filters) is True
        assert matches_filter("Rental Property Mortgage Payment", filters) is True

    def test_glob_prefix_only(self):
        filters = BillFilterConfig(categories=["Mortgage*"])
        assert matches_filter("Mortgage Payment", filters) is True
        assert matches_filter("Rental Property Mortgage", filters) is False

    def test_glob_suffix(self):
        filters = BillFilterConfig(categories=["*Utilities"])
        assert matches_filter("Lake House Utilities", filters) is True
        assert matches_filter("Cabin Utilities", filters) is True
        assert matches_filter("Utilities", filters) is True

    def test_case_insensitive(self):
        filters = BillFilterConfig(categories=["*mortgage*"])
        assert matches_filter("MORTGAGE", filters) is True
        assert matches_filter("Rental Property Mortgage", filters) is True

    def test_empty_category_returns_false(self):
        filters = BillFilterConfig(categories=["*Mortgage*"])
        assert matches_filter("", filters) is False

    def test_empty_filters_returns_false(self):
        filters = BillFilterConfig(categories=[])
        assert matches_filter("Mortgage", filters) is False

    def test_multiple_patterns_any_match(self):
        filters = BillFilterConfig(categories=["Water", "*Insurance*", "Phone"])
        assert matches_filter("Water", filters) is True
        assert matches_filter("Auto Insurance", filters) is True
        assert matches_filter("Phone", filters) is True
        assert matches_filter("Shopping", filters) is False


class TestGetBillFilters:
    def test_returns_empty_when_no_config(self, config_dir):
        result = get_bill_filters()
        assert result.categories == []

    def test_returns_saved_filters(self, config_dir):
        config = BillsConfig(
            bill_filters=BillFilterConfig(categories=["*Mortgage*", "Water"])
        )
        config_dir.mkdir(parents=True, exist_ok=True)
        save_config(config)
        result = get_bill_filters()
        assert result.categories == ["*Mortgage*", "Water"]


class TestSetBillFilters:
    def test_replaces_all_patterns(self, config_dir):
        config_dir.mkdir(parents=True, exist_ok=True)
        config = BillsConfig(
            bill_filters=BillFilterConfig(categories=["old_pattern"])
        )
        save_config(config)

        result = set_bill_filters(["*Mortgage*", "Water", "Phone"])
        assert result.categories == ["*Mortgage*", "Water", "Phone"]

        loaded = load_config()
        assert loaded.bill_filters.categories == ["*Mortgage*", "Water", "Phone"]


class TestAddBillFilter:
    def test_adds_new_pattern(self, config_dir):
        result = add_bill_filter("*Mortgage*")
        assert "*Mortgage*" in result.categories

    def test_no_duplicate(self, config_dir):
        add_bill_filter("*Mortgage*")
        result = add_bill_filter("*Mortgage*")
        assert result.categories.count("*Mortgage*") == 1


class TestRemoveBillFilter:
    def test_removes_existing_pattern(self, config_dir):
        add_bill_filter("*Mortgage*")
        add_bill_filter("Water")
        success, _ = remove_bill_filter("*Mortgage*")
        assert success is True
        result = get_bill_filters()
        assert "*Mortgage*" not in result.categories
        assert "Water" in result.categories

    def test_returns_false_for_missing_pattern(self, config_dir):
        success, msg = remove_bill_filter("nonexistent")
        assert success is False
        assert "not found" in msg.lower()
