"""Configuration management with XDG paths and typed entities."""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


# =============================================================================
# XDG Paths
# =============================================================================


def get_config_dir() -> Path:
    """Get XDG config directory for bills."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(xdg_config) / "bills"


def get_data_dir() -> Path:
    """Get XDG data directory for bills."""
    xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return Path(xdg_data) / "bills"


def get_config_path() -> Path:
    """Get path to config.yaml."""
    return get_config_dir() / "config.yaml"


# =============================================================================
# Entity Models
# =============================================================================


class PromoFinancing(BaseModel):
    """A promo financing plan (Citi Flex, Best Buy 0%, Chase Plan, etc.)."""

    description: Optional[str] = Field(default=None, description="Plan identifier, e.g. 'Plan 4', 'TV purchase'")
    balance: float = Field(description="Current balance on this promo")
    expires: Optional[str] = Field(default=None, description="Promo expiration YYYY-MM-DD")
    payment_amount: Optional[float] = Field(default=None, description="Payment amount for this promo")
    payments_remaining: Optional[int] = Field(default=None, description="Number of payments left")
    monthly_fee: Optional[float] = Field(default=None, description="Monthly fee if any (Citi Flex)")
    updated: Optional[str] = Field(default=None, description="When balance was last verified YYYY-MM-DD")


class CreditAccount(BaseModel):
    """A credit account (card, line of credit, store account)."""

    name: str = Field(description="Display name, e.g. 'Best Buy', 'Sapphire Preferred'")
    last4: Optional[str] = Field(default=None, description="Last 4 digits of account number")
    issuer: str = Field(description="Card issuer/servicer, e.g. 'Citi', 'Chase', 'Synchrony'")
    monarch_account_id: Optional[str] = Field(
        default=None, description="Monarch account ID for balance/credential lookups"
    )
    monarch_merchant_id: Optional[str] = Field(
        default=None, description="Monarch merchant ID for the payment recurring stream"
    )
    vendor: bool = Field(
        default=False,
        description="True for vendor/store financing (Best Buy, CareCredit) - typically used for promo financing",
    )
    due_day: Optional[int] = Field(default=None, description="Day of month payment is due (1-31)")
    payment_method: str = Field(
        default="manual",
        description="How payments are made: auto_pay_full, auto_pay_min, manual",
    )
    funding_account: Optional[str] = Field(
        default=None, description="Last4 of account that pays this"
    )
    promos: list[PromoFinancing] = Field(default_factory=list, description="Promo financing plans on this account")
    notes: Optional[str] = Field(default=None, description="Account-specific notes, PDF mappings, etc.")


class PropertyBill(BaseModel):
    """A bill associated with a property."""

    name: str = Field(description="Bill type, e.g. 'Mortgage', 'Water', 'Trash'")
    vendor: str = Field(description="Vendor name, e.g. 'Mortgage Company', 'City Water Dept'")
    monarch_merchant_id: Optional[str] = Field(
        default=None, description="Monarch merchant ID for deterministic stream lookup"
    )
    due_day: Optional[int] = Field(default=None, description="Day of month due (1-31)")
    amount: Optional[float] = Field(default=None, description="Expected amount")
    payment_method: str = Field(
        default="manual",
        description="How payments are made: auto_draft, auto_pay, manual",
    )
    funding_account: Optional[str] = Field(
        default=None, description="Last4 of account that pays this"
    )
    managed_by: Optional[str] = Field(
        default=None, description="Who manages this bill, e.g. 'spouse'. If set, only check for problems."
    )
    notes: Optional[str] = Field(default=None, description="Bill-specific notes")


class Property(BaseModel):
    """A property with associated bills."""

    name: str = Field(description="Property name, e.g. 'Primary Residence', 'Rental 1'")
    type: str = Field(
        default="residence",
        description="Type: residence, rental_longterm, rental_vacation, rental, land, personal",
    )
    has_mortgage: bool = Field(
        default=True,
        description="Whether this property has a mortgage. Set false for paid-off or unfinanced properties.",
    )
    address: Optional[str] = Field(default=None, description="Property address")
    tax_id: Optional[str] = Field(default=None, description="Property tax ID or parcel number")
    bills: list[PropertyBill] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None, description="Property-specific notes")


class FundingAccount(BaseModel):
    """A checking/savings account used to pay bills."""

    name: str = Field(description="Display name, e.g. 'Chase Checking'")
    last4: str = Field(description="Last 4 digits of account number")
    bank: str = Field(description="Bank name, e.g. 'Chase', 'Ally'")
    monarch_id: Optional[str] = Field(default=None, description="Monarch account ID for balance lookups")
    notes: Optional[str] = Field(default=None, description="Account-specific notes")


class BudgetScopeConfig(BaseModel):
    """Which expenses to include in cash flow calculations."""

    properties_residence: bool = Field(default=True, description="Include primary residence bills")
    properties_rental: bool = Field(default=False, description="Include rental property bills")
    credit: bool = Field(default=True, description="Include credit accounts")
    subscriptions: bool = Field(default=True, description="Include subscriptions")


class IgnoredMerchant(BaseModel):
    """A Monarch merchant explicitly classified as ignorable."""

    merchant_id: str = Field(description="Monarch merchant ID")
    name: str = Field(description="Human-readable label (not used for matching)")
    reason: str = Field(description="Why ignored: subscription_inconsequential, income, transfer, etc.")


class BillFilterConfig(BaseModel):
    """Category patterns for filtering Monarch's list_recurring to consequential bills.

    Patterns use glob-style matching (fnmatch) against Monarch category names.
    Bills that match are those with consequences for non-payment: credit damage,
    service disconnection, foreclosure, etc.
    """

    categories: list[str] = Field(
        default_factory=list,
        description="Glob patterns matching Monarch category names, e.g. '*Mortgage*', 'Water'",
    )


class BillsConfig(BaseModel):
    """Root configuration model."""

    version: int = Field(default=1, description="Config schema version")
    credit_accounts: list[CreditAccount] = Field(default_factory=list)
    properties: list[Property] = Field(default_factory=list)
    funding_accounts: list[FundingAccount] = Field(default_factory=list)
    ignored_merchants: list[IgnoredMerchant] = Field(default_factory=list)
    budget_scope: BudgetScopeConfig = Field(default_factory=BudgetScopeConfig)
    bill_filters: BillFilterConfig = Field(default_factory=BillFilterConfig)


# =============================================================================
# Load / Save
# =============================================================================


def load_config() -> BillsConfig:
    """Load typed config from XDG path.

    Returns empty config if file doesn't exist.
    """
    config_path = get_config_path()
    if not config_path.exists():
        return BillsConfig()

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    return BillsConfig.model_validate(data)


def save_config(config: BillsConfig) -> None:
    """Save typed config to XDG path."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(exclude_none=True)
    with open(config_path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
