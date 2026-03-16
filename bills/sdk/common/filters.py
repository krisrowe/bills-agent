"""SDK functions for bill filter management."""

from fnmatch import fnmatch

from .config import load_config, save_config, BillFilterConfig


def get_bill_filters() -> BillFilterConfig:
    """Get current bill filter configuration."""
    config = load_config()
    return config.bill_filters


def set_bill_filters(categories: list[str]) -> BillFilterConfig:
    """Replace the entire category filter list."""
    config = load_config()
    config.bill_filters.categories = categories
    save_config(config)
    return config.bill_filters


def add_bill_filter(pattern: str) -> BillFilterConfig:
    """Add a category pattern to the filter list.

    No-op if pattern already exists.
    """
    config = load_config()
    if pattern not in config.bill_filters.categories:
        config.bill_filters.categories.append(pattern)
        save_config(config)
    return config.bill_filters


def remove_bill_filter(pattern: str) -> tuple[bool, str]:
    """Remove a category pattern from the filter list.

    Returns (success, message).
    """
    config = load_config()
    if pattern in config.bill_filters.categories:
        config.bill_filters.categories.remove(pattern)
        save_config(config)
        return True, f"Removed filter: {pattern}"
    return False, f"Pattern not found: {pattern}"


def matches_filter(category_name: str, filters: BillFilterConfig) -> bool:
    """Check if a Monarch category name matches any configured filter pattern.

    Uses fnmatch for glob-style matching (case-insensitive).
    Returns True if category matches any pattern in the filter list.
    """
    if not category_name:
        return False
    lower_cat = category_name.lower()
    for pattern in filters.categories:
        if fnmatch(lower_cat, pattern.lower()):
            return True
    return False
