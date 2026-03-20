"""Tests for property inheritance SDK functions."""

import pytest

from bills.sdk.common.config import (
    BillsConfig,
    Property,
    PropertyBill,
    save_config,
)
from bills.sdk.common.properties import (
    InheritedBillError,
    get_resolved_property,
    list_properties,
    remove_property_bill,
    update_property_bill,
)


def _write_config(config: BillsConfig, config_dir) -> None:
    """Write a BillsConfig to the isolated config dir."""
    config_dir.mkdir(parents=True, exist_ok=True)
    save_config(config)


# =============================================================================
# remove_property_bill
# =============================================================================


class TestRemovePropertyBill:
    def test_remove_inherited_bill_raises_error(self, config_dir):
        """Removing a bill that comes from inheritance raises InheritedBillError."""
        # residence template has Mortgage (via real_estate), Electric/Gas, etc.
        # The package config.yaml provides residence -> real_estate.
        # We set up a property that inherits residence (from the real package config).
        config = BillsConfig(
            properties=[
                Property(name="Home", inherit="residence"),
            ]
        )
        _write_config(config, config_dir)

        with pytest.raises(InheritedBillError):
            remove_property_bill("Home", "Mortgage")

    def test_remove_locally_added_bill_succeeds(self, config_dir):
        """Removing a bill added directly to the property (not inherited) succeeds."""
        config = BillsConfig(
            properties=[
                Property(
                    name="Home",
                    inherit="residence",
                    bills=[PropertyBill(name="HOA", vendor="HOA Board")],
                )
            ]
        )
        _write_config(config, config_dir)

        success, msg = remove_property_bill("Home", "HOA")
        assert success is True
        assert "HOA" in msg

        # Verify HOA is no longer in config
        from bills.sdk.common.config import load_config
        reloaded = load_config()
        home = next(p for p in reloaded.properties if p.name == "Home")
        bill_names = [b.name for b in home.bills]
        assert "HOA" not in bill_names


# =============================================================================
# update_property_bill
# =============================================================================


class TestUpdatePropertyBill:
    def test_update_inherited_bill_creates_local_override(self, config_dir):
        """Updating an inherited bill that has no local entry creates a local override."""
        config = BillsConfig(
            properties=[
                Property(name="Home", inherit="residence"),
            ]
        )
        _write_config(config, config_dir)

        # Mortgage is inherited from real_estate via residence; no local entry
        success, result = update_property_bill("Home", "Mortgage", vendor="Big Lender")
        assert success is True
        assert result.name == "Mortgage"
        assert result.vendor == "Big Lender"

        # Verify the override was persisted to config
        from bills.sdk.common.config import load_config
        reloaded = load_config()
        home = next(p for p in reloaded.properties if p.name == "Home")
        local_mortgage = next((b for b in home.bills if b.name == "Mortgage"), None)
        assert local_mortgage is not None
        assert local_mortgage.vendor == "Big Lender"


# =============================================================================
# list_properties
# =============================================================================


class TestListProperties:
    def test_list_properties_excludes_abstract_by_default(self, config_dir):
        """list_properties() without include_abstract omits abstract properties."""
        config = BillsConfig(
            properties=[
                Property(name="MyTemplate", abstract=True, bills=[PropertyBill(name="Property Tax")]),
                Property(name="Real Property", inherit="MyTemplate"),
            ]
        )
        _write_config(config, config_dir)

        result = list_properties()
        names = [p.name for p in result]
        assert "MyTemplate" not in names
        assert "Real Property" in names

    def test_list_properties_includes_abstract_when_requested(self, config_dir):
        """list_properties(include_abstract=True) returns abstract templates too."""
        config = BillsConfig(
            properties=[
                Property(name="MyTemplate", abstract=True, bills=[PropertyBill(name="Property Tax")]),
                Property(name="Real Property", inherit="MyTemplate"),
            ]
        )
        _write_config(config, config_dir)

        result = list_properties(include_abstract=True)
        names = [p.name for p in result]
        # Package-level abstract templates should also be included
        assert "MyTemplate" in names
        assert "Real Property" in names
        assert "residence" in names  # from package config


# =============================================================================
# get_resolved_property
# =============================================================================


class TestGetResolvedProperty:
    def test_get_resolved_property_applies_inheritance(self, config_dir):
        """get_resolved_property returns merged bill list with inheritance applied."""
        # residence (package config) inherits real_estate: Mortgage, Property Tax, Electric/Gas, etc.
        config = BillsConfig(
            properties=[
                Property(
                    name="Home",
                    inherit="residence",
                    bills=[PropertyBill(name="HOA", vendor="HOA Board")],
                )
            ]
        )
        _write_config(config, config_dir)

        prop, resolved = get_resolved_property("Home")
        assert prop is not None
        assert prop.name == "Home"

        bill_names = {b.name for b in resolved}
        # Inherited from real_estate (via residence)
        assert "Mortgage" in bill_names
        assert "Property Tax" in bill_names
        # Inherited from residence directly
        assert "Electric/Gas" in bill_names
        # Locally added
        assert "HOA" in bill_names


# =============================================================================
# funding_account
# =============================================================================


class TestFundingAccount:
    def test_funding_account_on_property(self, config_dir):
        """Setting funding_account on a property persists across load/save."""
        from bills.sdk.common.properties import update_property

        config = BillsConfig(
            properties=[
                Property(name="Home", inherit="residence"),
            ]
        )
        _write_config(config, config_dir)

        success, result = update_property("Home", funding_account="1234")
        assert success is True
        assert result.funding_account == "1234"

        from bills.sdk.common.config import load_config
        reloaded = load_config()
        home = next(p for p in reloaded.properties if p.name == "Home")
        assert home.funding_account == "1234"
