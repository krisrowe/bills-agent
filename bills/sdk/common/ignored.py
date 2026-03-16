"""SDK functions for ignored merchant management."""

from .config import IgnoredMerchant, load_config, save_config


def list_ignored_merchants() -> list[IgnoredMerchant]:
    """List all ignored merchants."""
    config = load_config()
    return config.ignored_merchants


def add_ignored_merchant(
    merchant_id: str,
    name: str,
    reason: str,
) -> tuple[bool, IgnoredMerchant | str]:
    """Add a merchant to the ignored list.

    No-op if merchant_id already exists.
    Returns (success, merchant_or_error).
    """
    config = load_config()

    for m in config.ignored_merchants:
        if m.merchant_id == merchant_id:
            return False, f"Merchant {merchant_id} ({m.name}) already ignored"

    entry = IgnoredMerchant(
        merchant_id=merchant_id,
        name=name,
        reason=reason,
    )
    config.ignored_merchants.append(entry)
    save_config(config)
    return True, entry


def remove_ignored_merchant(merchant_id: str) -> tuple[bool, str]:
    """Remove a merchant from the ignored list.

    Returns (success, message).
    """
    config = load_config()

    for i, m in enumerate(config.ignored_merchants):
        if m.merchant_id == merchant_id:
            removed = config.ignored_merchants.pop(i)
            save_config(config)
            return True, f"Removed: {removed.name} ({removed.merchant_id})"

    return False, f"Merchant {merchant_id} not in ignored list"
