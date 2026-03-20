"""SDK functions for property management."""

from typing import Optional

from .config import (
    Property,
    PropertyBill,
    load_config,
    save_config,
)
from .inventory import load_package_config, resolve_bills


def list_properties(include_abstract: bool = False) -> list[Property]:
    """List all properties. By default excludes abstract templates and deleted properties."""
    config = load_config()
    if include_abstract:
        defaults = load_package_config()
        all_props = defaults.properties + config.properties
        return [p for p in all_props if not p.deleted]
    return [p for p in config.properties if not p.abstract and not p.deleted]


def get_property(name: str) -> Optional[Property]:
    """Get a property by name (case-insensitive). Checks config and defaults."""
    config = load_config()
    for prop in config.properties:
        if prop.name.lower() == name.lower() and not prop.deleted:
            return prop
    defaults = load_package_config()
    for prop in defaults.properties:
        if prop.name.lower() == name.lower() and not prop.deleted:
            return prop
    return None


def get_resolved_property(name: str) -> Optional[tuple[Property, list[PropertyBill]]]:
    """Get a property with its fully resolved bill list (inheritance applied).

    Returns (property, resolved_bills) or None if not found.
    """
    config = load_config()
    defaults = load_package_config()
    all_properties = defaults.properties + config.properties

    prop = None
    for p in config.properties:
        if p.name.lower() == name.lower() and not p.deleted:
            prop = p
            break
    if prop is None:
        for p in defaults.properties:
            if p.name.lower() == name.lower() and not p.deleted:
                prop = p
                break
    if prop is None:
        return None

    resolved = resolve_bills(prop, all_properties)
    return prop, resolved


def list_property_bills(property_name: str) -> tuple[Optional[Property], list[PropertyBill]]:
    """List declared bills for a property (inheritance applied).

    Returns (property_or_none, resolved_bills).
    """
    result = get_resolved_property(property_name)
    if result is None:
        return None, []
    return result


def _is_inherited_bill(prop: Property, bill_name: str) -> bool:
    """Check if a bill name comes from the inheritance chain (not locally declared)."""
    defaults = load_package_config()
    all_properties = defaults.properties + [p for p in load_config().properties if p.name != prop.name]

    if not prop.inherit:
        return False

    parent = next((p for p in all_properties if p.name == prop.inherit), None)
    if parent is None:
        return False

    parent_bills = resolve_bills(parent, all_properties)
    return any(b.name.lower() == bill_name.lower() for b in parent_bills)


def update_property(
    name: str,
    *,
    inherit: Optional[str] = None,
    abstract: Optional[bool] = None,
    funding_account: Optional[str] = None,
    address: Optional[str] = None,
    tax_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> tuple[bool, str | Property]:
    """Update an existing property.

    Returns (success, property_or_error).
    """
    config = load_config()

    for i, prop in enumerate(config.properties):
        if prop.name.lower() == name.lower():
            if inherit is not None:
                prop.inherit = inherit
            if abstract is not None:
                prop.abstract = abstract
            if funding_account is not None:
                prop.funding_account = funding_account
            if address is not None:
                prop.address = address
            if tax_id is not None:
                prop.tax_id = tax_id
            if notes is not None:
                prop.notes = notes

            config.properties[i] = prop
            save_config(config)
            return True, prop

    return False, f"No property named '{name}'"


def register_property_bill(
    property_name: str,
    bill_name: str,
    vendor: Optional[str] = None,
    due_day: Optional[int] = None,
    amount: Optional[float] = None,
    payment_method: Optional[str] = None,
    funding_account: Optional[str] = None,
    inherit: Optional[str] = None,
    managed_by: Optional[str] = None,
    monarch_merchant_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> tuple[bool, str | PropertyBill]:
    """Register a new property bill.

    Creates property if it doesn't exist. If the bill was previously deleted
    (tombstone), removes the tombstone and creates fresh.
    Returns (success, bill_or_error).
    """
    config = load_config()

    # Find or create property
    prop = None
    prop_idx = None
    for i, p in enumerate(config.properties):
        if p.name.lower() == property_name.lower():
            prop = p
            prop_idx = i
            break

    if prop is None:
        prop = Property(name=property_name, inherit=inherit)
        config.properties.append(prop)
        prop_idx = len(config.properties) - 1

    # Check for existing bill — if deleted tombstone, remove it first
    for j, bill in enumerate(prop.bills):
        if bill.name.lower() == bill_name.lower():
            if bill.deleted:
                prop.bills.pop(j)
                break
            return False, f"Bill '{bill_name}' already exists for {property_name}"

    new_bill = PropertyBill(
        name=bill_name,
        vendor=vendor,
        due_day=due_day,
        amount=amount,
        payment_method=payment_method,
        funding_account=funding_account,
        managed_by=managed_by,
        monarch_merchant_id=monarch_merchant_id,
        notes=notes,
    )
    prop.bills.append(new_bill)
    config.properties[prop_idx] = prop
    save_config(config)
    return True, new_bill


def update_property_bill(
    property_name: str,
    bill_name: str,
    *,
    vendor: Optional[str] = None,
    monarch_merchant_id: Optional[str] = None,
    due_day: Optional[int] = None,
    amount: Optional[float] = None,
    payment_method: Optional[str] = None,
    funding_account: Optional[str] = None,
    managed_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> tuple[bool, str | PropertyBill]:
    """Update an existing property bill. Creates a local override if the bill is inherited.

    Returns (success, bill_or_error).
    """
    config = load_config()

    for i, prop in enumerate(config.properties):
        if prop.name.lower() != property_name.lower():
            continue

        # Find existing local bill entry
        for j, bill in enumerate(prop.bills):
            if bill.name.lower() != bill_name.lower():
                continue
            if bill.deleted:
                return False, f"Bill '{bill_name}' is deleted on {property_name}. Use register to re-add."

            if vendor is not None:
                bill.vendor = vendor
            if monarch_merchant_id is not None:
                bill.monarch_merchant_id = monarch_merchant_id
            if due_day is not None:
                bill.due_day = due_day
            if amount is not None:
                bill.amount = amount
            if payment_method is not None:
                bill.payment_method = payment_method
            if funding_account is not None:
                bill.funding_account = funding_account
            if managed_by is not None:
                bill.managed_by = managed_by
            if notes is not None:
                bill.notes = notes

            prop.bills[j] = bill
            config.properties[i] = prop
            save_config(config)
            return True, bill

        # Bill not in local list — might be inherited. Create local override.
        if _is_inherited_bill(prop, bill_name):
            override = PropertyBill(
                name=bill_name,
                vendor=vendor,
                monarch_merchant_id=monarch_merchant_id,
                due_day=due_day,
                amount=amount,
                payment_method=payment_method,
                funding_account=funding_account,
                managed_by=managed_by,
                notes=notes,
            )
            prop.bills.append(override)
            config.properties[i] = prop
            save_config(config)
            return True, override

        return False, f"No bill '{bill_name}' on property '{property_name}'"

    return False, f"No property named '{property_name}'"


def remove_property_bill(
    property_name: str,
    bill_name: str,
) -> tuple[bool, str]:
    """Remove a bill from a property.

    If the bill is inherited, writes a deleted tombstone to suppress it.
    If the bill is locally added, removes the entry entirely.
    Returns (success, message).
    """
    config = load_config()

    for i, prop in enumerate(config.properties):
        if prop.name.lower() != property_name.lower():
            continue

        # Check if locally declared
        for j, bill in enumerate(prop.bills):
            if bill.name.lower() != bill_name.lower():
                continue
            if bill.deleted:
                return False, f"Bill '{bill_name}' is already removed from {property_name}"

            if _is_inherited_bill(prop, bill_name):
                # It's in our local list as an override of an inherited bill — mark deleted
                bill.deleted = True
                prop.bills[j] = bill
            else:
                # Purely local — just remove
                prop.bills.pop(j)

            config.properties[i] = prop
            save_config(config)
            return True, f"Removed '{bill_name}' from {property_name}"

        # Not in local list — check if inherited
        if _is_inherited_bill(prop, bill_name):
            # Add tombstone
            tombstone = PropertyBill(name=bill_name, deleted=True)
            prop.bills.append(tombstone)
            config.properties[i] = prop
            save_config(config)
            return True, f"Removed '{bill_name}' from {property_name}"

        return False, f"No bill '{bill_name}' on property '{property_name}'"

    return False, f"No property named '{property_name}'"
