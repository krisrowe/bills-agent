"""Tests for config module - XDG paths and config load/save."""

from pathlib import Path

import pytest

from bills.sdk.common.config import (
    BillsConfig,
    BudgetScopeConfig,
    CreditAccount,
    PromoFinancing,
    get_config_dir,
    get_config_path,
    load_config,
    save_config,
)


class TestXdgPaths:
    def test_uses_xdg_config_home_when_set(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert get_config_dir() == tmp_path / "bills"

    def test_falls_back_to_dot_config_when_unset(self, monkeypatch):
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = get_config_dir()
        assert result == Path.home() / ".config" / "bills"

    def test_config_path_is_yaml_in_config_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert get_config_path() == tmp_path / "bills" / "config.yaml"


class TestLoadConfig:
    def test_returns_empty_config_when_no_file(self, config_dir):
        config = load_config()
        assert config.version == 1
        assert config.credit_accounts == []
        assert config.properties == []
        assert config.funding_accounts == []

    def test_loads_credit_account_from_yaml(self, config_dir):
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text("""
version: 1
credit_accounts:
  - name: Test Card
    issuer: Test Bank
    last4: "1234"
""")
        config = load_config()
        assert len(config.credit_accounts) == 1
        assert config.credit_accounts[0].name == "Test Card"
        assert config.credit_accounts[0].last4 == "1234"

    def test_loads_promo_array_from_yaml(self, config_dir):
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text("""
version: 1
credit_accounts:
  - name: Best Buy
    issuer: Synchrony
    vendor: true
    promos:
      - description: TV purchase
        balance: 1200.00
        expires: "2026-06-14"
        updated: "2026-01-15"
      - description: Appliance
        balance: 800.00
        expires: "2026-12-01"
""")
        config = load_config()
        acct = config.credit_accounts[0]
        assert len(acct.promos) == 2
        assert acct.promos[0].description == "TV purchase"
        assert acct.promos[0].balance == 1200.00
        assert acct.promos[0].updated == "2026-01-15"
        assert acct.promos[1].balance == 800.00


class TestSaveConfig:
    def test_creates_config_dir_when_missing(self, config_dir):
        config = BillsConfig()
        save_config(config)
        assert (config_dir / "config.yaml").exists()

    def test_saved_credit_account_loads_with_same_values(self, config_dir):
        config = BillsConfig(
            credit_accounts=[
                CreditAccount(name="Visa Rewards", issuer="Chase", last4="9876")
            ]
        )
        save_config(config)

        loaded = load_config()
        assert len(loaded.credit_accounts) == 1
        assert loaded.credit_accounts[0].name == "Visa Rewards"
        assert loaded.credit_accounts[0].last4 == "9876"

    def test_saved_promo_preserves_all_fields(self, config_dir):
        promo = PromoFinancing(
            description="Flex Plan 1",
            balance=2500.00,
            expires="2026-08-15",
            payment_amount=250.00,
            payments_remaining=10,
            monthly_fee=1.99,
            updated="2026-01-20",
        )
        config = BillsConfig(
            credit_accounts=[
                CreditAccount(
                    name="Citi Double Cash",
                    issuer="Citi",
                    last4="4321",
                    promos=[promo],
                )
            ]
        )
        save_config(config)

        loaded = load_config()
        loaded_promo = loaded.credit_accounts[0].promos[0]
        assert loaded_promo.description == "Flex Plan 1"
        assert loaded_promo.balance == 2500.00
        assert loaded_promo.expires == "2026-08-15"
        assert loaded_promo.payment_amount == 250.00
        assert loaded_promo.payments_remaining == 10
        assert loaded_promo.monthly_fee == 1.99
        assert loaded_promo.updated == "2026-01-20"

    def test_saved_budget_scope_loads_with_changed_values(self, config_dir):
        config = BillsConfig(
            budget_scope=BudgetScopeConfig(
                properties_residence=False,
                properties_rental=True,
                credit=False,
            )
        )
        save_config(config)

        loaded = load_config()
        assert loaded.budget_scope.properties_residence is False
        assert loaded.budget_scope.properties_rental is True
        assert loaded.budget_scope.credit is False

    def test_excludes_none_values_from_yaml(self, config_dir):
        config = BillsConfig(
            credit_accounts=[
                CreditAccount(name="Minimal", issuer="Bank")
            ]
        )
        save_config(config)

        yaml_content = (config_dir / "config.yaml").read_text()
        assert "null" not in yaml_content
        assert "None" not in yaml_content


class TestBudgetScopeDefaults:
    def test_includes_residence_credit_subscriptions_by_default(self):
        scope = BudgetScopeConfig()
        assert scope.properties_residence is True
        assert scope.credit is True
        assert scope.subscriptions is True

    def test_excludes_rental_by_default(self):
        scope = BudgetScopeConfig()
        assert scope.properties_rental is False


class TestCreditAccountDefaults:
    def test_vendor_defaults_false(self):
        acct = CreditAccount(name="Test", issuer="Bank")
        assert acct.vendor is False

    def test_payment_method_defaults_manual(self):
        acct = CreditAccount(name="Test", issuer="Bank")
        assert acct.payment_method == "manual"

    def test_promos_defaults_empty_list(self):
        acct = CreditAccount(name="Test", issuer="Bank")
        assert acct.promos == []

    def test_notes_defaults_none(self):
        acct = CreditAccount(name="Test", issuer="Bank")
        assert acct.notes is None


class TestPromoFinancingModel:
    def test_only_balance_required(self):
        promo = PromoFinancing(balance=500.00)
        assert promo.balance == 500.00
        assert promo.description is None
        assert promo.expires is None
        assert promo.updated is None

    def test_all_fields_populate(self):
        promo = PromoFinancing(
            description="Plan 4",
            balance=1500.00,
            expires="2026-09-30",
            payment_amount=150.00,
            payments_remaining=10,
            monthly_fee=2.50,
            updated="2026-01-27",
        )
        assert promo.description == "Plan 4"
        assert promo.balance == 1500.00
        assert promo.expires == "2026-09-30"
        assert promo.payment_amount == 150.00
        assert promo.payments_remaining == 10
        assert promo.monthly_fee == 2.50
        assert promo.updated == "2026-01-27"
