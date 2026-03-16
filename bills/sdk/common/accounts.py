"""SDK functions for account management."""

from typing import Optional

from .config import (
    CreditAccount,
    FundingAccount,
    PromoFinancing,
    load_config,
    save_config,
)


# =============================================================================
# Credit Accounts
# =============================================================================


def list_credit_accounts() -> list[CreditAccount]:
    """List all credit accounts."""
    config = load_config()
    return config.credit_accounts


def get_credit_account(last4: str) -> Optional[CreditAccount]:
    """Get a credit account by last4."""
    config = load_config()
    for acct in config.credit_accounts:
        if acct.last4 == last4:
            return acct
    return None


def register_credit_account(
    name: str,
    issuer: str,
    last4: Optional[str] = None,
    due_day: Optional[int] = None,
    payment_method: str = "manual",
    funding_account: Optional[str] = None,
    vendor: bool = False,
    notes: Optional[str] = None,
) -> tuple[bool, CreditAccount | str]:
    """Register a new credit account.

    Returns (success, account_or_error).
    Use add_promo() to add promo financing plans after registration.
    """
    config = load_config()

    if last4:
        for acct in config.credit_accounts:
            if acct.last4 == last4:
                return False, f"Account with last4={last4} already exists"

    new_acct = CreditAccount(
        name=name,
        last4=last4,
        issuer=issuer,
        vendor=vendor,
        due_day=due_day,
        payment_method=payment_method,
        funding_account=funding_account,
        notes=notes,
    )
    config.credit_accounts.append(new_acct)
    save_config(config)
    return True, new_acct


def update_credit_account(
    last4: str,
    *,
    name: Optional[str] = None,
    issuer: Optional[str] = None,
    due_day: Optional[int] = None,
    payment_method: Optional[str] = None,
    funding_account: Optional[str] = None,
    vendor: Optional[bool] = None,
    notes: Optional[str] = None,
) -> tuple[bool, CreditAccount | str]:
    """Update an existing credit account.

    Returns (success, account_or_error).
    Use add_promo/update_promo/remove_promo for promo financing plans.
    """
    config = load_config()

    for i, acct in enumerate(config.credit_accounts):
        if acct.last4 == last4:
            if name is not None:
                acct.name = name
            if issuer is not None:
                acct.issuer = issuer
            if due_day is not None:
                acct.due_day = due_day
            if payment_method is not None:
                acct.payment_method = payment_method
            if funding_account is not None:
                acct.funding_account = funding_account
            if vendor is not None:
                acct.vendor = vendor
            if notes is not None:
                acct.notes = notes

            config.credit_accounts[i] = acct
            save_config(config)
            return True, acct

    return False, f"No account with last4={last4}"


def list_promo_accounts() -> list[CreditAccount]:
    """List credit accounts with active promo financing."""
    config = load_config()
    return [acct for acct in config.credit_accounts if len(acct.promos) > 0]


# =============================================================================
# Promo Financing Management
# =============================================================================


def add_promo(
    account_last4: str,
    balance: float,
    description: Optional[str] = None,
    expires: Optional[str] = None,
    payment_amount: Optional[float] = None,
    payments_remaining: Optional[int] = None,
    monthly_fee: Optional[float] = None,
    updated: Optional[str] = None,
) -> tuple[bool, PromoFinancing | str]:
    """Add a promo financing plan to a credit account.

    Returns (success, promo_or_error).
    """
    config = load_config()

    for i, acct in enumerate(config.credit_accounts):
        if acct.last4 == account_last4:
            promo = PromoFinancing(
                description=description,
                balance=balance,
                expires=expires,
                payment_amount=payment_amount,
                payments_remaining=payments_remaining,
                monthly_fee=monthly_fee,
                updated=updated,
            )
            acct.promos.append(promo)
            config.credit_accounts[i] = acct
            save_config(config)
            return True, promo

    return False, f"No account with last4={account_last4}"


def update_promo(
    account_last4: str,
    promo_index: int,
    *,
    description: Optional[str] = None,
    balance: Optional[float] = None,
    expires: Optional[str] = None,
    payment_amount: Optional[float] = None,
    payments_remaining: Optional[int] = None,
    monthly_fee: Optional[float] = None,
    updated: Optional[str] = None,
) -> tuple[bool, PromoFinancing | str]:
    """Update a promo financing plan on a credit account.

    promo_index is 0-based index into the promos array.
    Returns (success, promo_or_error).
    """
    config = load_config()

    for i, acct in enumerate(config.credit_accounts):
        if acct.last4 == account_last4:
            if promo_index < 0 or promo_index >= len(acct.promos):
                return False, f"Promo index {promo_index} out of range (0-{len(acct.promos)-1})"

            promo = acct.promos[promo_index]
            if description is not None:
                promo.description = description
            if balance is not None:
                promo.balance = balance
            if expires is not None:
                promo.expires = expires
            if payment_amount is not None:
                promo.payment_amount = payment_amount
            if payments_remaining is not None:
                promo.payments_remaining = payments_remaining
            if monthly_fee is not None:
                promo.monthly_fee = monthly_fee
            if updated is not None:
                promo.updated = updated

            acct.promos[promo_index] = promo
            config.credit_accounts[i] = acct
            save_config(config)
            return True, promo

    return False, f"No account with last4={account_last4}"


def remove_promo(
    account_last4: str,
    promo_index: int,
) -> tuple[bool, str]:
    """Remove a promo financing plan from a credit account.

    promo_index is 0-based index into the promos array.
    Returns (success, message).
    """
    config = load_config()

    for i, acct in enumerate(config.credit_accounts):
        if acct.last4 == account_last4:
            if promo_index < 0 or promo_index >= len(acct.promos):
                return False, f"Promo index {promo_index} out of range (0-{len(acct.promos)-1})"

            removed = acct.promos.pop(promo_index)
            config.credit_accounts[i] = acct
            save_config(config)
            desc = removed.description or f"${removed.balance}"
            return True, f"Removed promo: {desc}"

    return False, f"No account with last4={account_last4}"


# =============================================================================
# Funding Accounts
# =============================================================================


def list_funding_accounts() -> list[FundingAccount]:
    """List all funding accounts."""
    config = load_config()
    return config.funding_accounts


def register_funding_account(
    name: str,
    last4: str,
    bank: str,
    monarch_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> tuple[bool, FundingAccount | str]:
    """Register a new funding account.

    Returns (success, account_or_error).
    """
    config = load_config()

    for acct in config.funding_accounts:
        if acct.last4 == last4:
            return False, f"Account with last4={last4} already exists"

    new_acct = FundingAccount(
        name=name,
        last4=last4,
        bank=bank,
        monarch_id=monarch_id,
        notes=notes,
    )
    config.funding_accounts.append(new_acct)
    save_config(config)
    return True, new_acct
