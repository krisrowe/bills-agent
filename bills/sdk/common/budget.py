"""SDK functions for budget scope management."""

from typing import Optional

from .config import BudgetScopeConfig, load_config, save_config


def get_budget_scope() -> BudgetScopeConfig:
    """Get current budget scope configuration."""
    config = load_config()
    return config.budget_scope


def update_budget_scope(
    *,
    properties_residence: Optional[bool] = None,
    properties_rental: Optional[bool] = None,
    credit: Optional[bool] = None,
    subscriptions: Optional[bool] = None,
) -> BudgetScopeConfig:
    """Update budget scope configuration.

    Only provided fields are changed.
    """
    config = load_config()

    if properties_residence is not None:
        config.budget_scope.properties_residence = properties_residence
    if properties_rental is not None:
        config.budget_scope.properties_rental = properties_rental
    if credit is not None:
        config.budget_scope.credit = credit
    if subscriptions is not None:
        config.budget_scope.subscriptions = subscriptions

    save_config(config)
    return config.budget_scope
