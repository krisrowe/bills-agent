"""SDK functions for property management."""

from typing import Optional

from .config import (
    Property,
    PropertyBill,
    load_config,
    save_config,
)


def list_properties() -> list[Property]:
    """List all properties."""
    config = load_config()
    return config.properties


def get_property(name: str) -> Optional[Property]:
    """Get a property by name (case-insensitive)."""
    config = load_config()
    for prop in config.properties:
        if prop.name.lower() == name.lower():
            return prop
    return None


def list_property_bills(property_name: str) -> tuple[Optional[Property], list[PropertyBill]]:
    """List bills for a property.

    Returns (property_or_none, bills).
    """
    prop = get_property(property_name)
    if prop is None:
        return None, []
    return prop, prop.bills


def update_property(
    name: str,
    *,
    address: Optional[str] = None,
    type: Optional[str] = None,
    has_mortgage: Optional[bool] = None,
    tax_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> tuple[bool, str | Property]:
    """Update an existing property.

    Returns (success, property_or_error).
    """
    config = load_config()

    for i, prop in enumerate(config.properties):
        if prop.name.lower() == name.lower():
            if address is not None:
                prop.address = address
            if type is not None:
                prop.type = type
            if has_mortgage is not None:
                prop.has_mortgage = has_mortgage
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
    vendor: str,
    due_day: Optional[int] = None,
    amount: Optional[float] = None,
    payment_method: str = "manual",
    funding_account: Optional[str] = None,
    type: str = "residence",
    has_mortgage: bool = True,
    managed_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> tuple[bool, str | PropertyBill]:
    """Register a new property bill.

    Creates property if it doesn't exist.
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
        prop = Property(name=property_name, type=type, has_mortgage=has_mortgage)
        config.properties.append(prop)
        prop_idx = len(config.properties) - 1

    # Check for duplicate bill
    for bill in prop.bills:
        if bill.name.lower() == bill_name.lower():
            return False, f"Bill '{bill_name}' already exists for {property_name}"

    new_bill = PropertyBill(
        name=bill_name,
        vendor=vendor,
        due_day=due_day,
        amount=amount,
        payment_method=payment_method,
        funding_account=funding_account,
        managed_by=managed_by,
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
    """Update an existing property bill.

    Returns (success, bill_or_error).
    Only provided fields are changed.
    """
    config = load_config()

    for i, prop in enumerate(config.properties):
        if prop.name.lower() != property_name.lower():
            continue
        for j, bill in enumerate(prop.bills):
            if bill.name.lower() != bill_name.lower():
                continue

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

    return False, f"No bill '{bill_name}' on property '{property_name}'"


def remove_property_bill(
    property_name: str,
    bill_name: str,
) -> tuple[bool, str]:
    """Remove a bill from a property.

    Returns (success, message).
    """
    config = load_config()

    for i, prop in enumerate(config.properties):
        if prop.name.lower() != property_name.lower():
            continue
        for j, bill in enumerate(prop.bills):
            if bill.name.lower() != bill_name.lower():
                continue

            prop.bills.pop(j)
            config.properties[i] = prop
            save_config(config)
            return True, f"Removed '{bill_name}' from {property_name}"

    return False, f"No bill '{bill_name}' on property '{property_name}'"
