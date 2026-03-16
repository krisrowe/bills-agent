"""Tests for bill inventory — ID-based join logic with accountability."""

from datetime import date

import pytest

from bills.sdk.common.config import (
    BillFilterConfig,
    BillsConfig,
    CreditAccount,
    IgnoredMerchant,
    PromoFinancing,
    Property,
    PropertyBill,
)
from bills.sdk.common.inventory import (
    AppDefaults,
    ExpectedBillSlot,
    InventoryAccountabilityError,
    PropertyTypeTemplate,
    SkipPatternGroup,
    build_bill_inventory,
    load_defaults,
)


# =============================================================================
# Helpers
# =============================================================================


def _defaults() -> AppDefaults:
    return AppDefaults(
        property_types={
            "residence": PropertyTypeTemplate(
                expected_bills=[
                    ExpectedBillSlot(slot="mortgage", name="Mortgage"),
                    ExpectedBillSlot(slot="electric_gas", name="Electric/Gas"),
                    ExpectedBillSlot(slot="water_trash", name="Water/Trash"),
                ]
            ),
            "rental_longterm": PropertyTypeTemplate(
                expected_bills=[
                    ExpectedBillSlot(slot="mortgage", name="Mortgage"),
                    ExpectedBillSlot(slot="insurance", name="Insurance"),
                    ExpectedBillSlot(slot="property_tax", name="Property Tax"),
                ]
            ),
            "land": PropertyTypeTemplate(
                expected_bills=[
                    ExpectedBillSlot(slot="property_tax", name="Property Tax"),
                ]
            ),
        },
        skip_patterns={
            "transfer": SkipPatternGroup(
                category_patterns=["*Transfer*", "Same Bank Transfer*"]
            ),
            "income": SkipPatternGroup(
                category_patterns=["*Salary*", "*Net Pay*", "Interest"]
            ),
        },
    )


def _stream(
    stream_id="100",
    merchant="Vendor",
    merchant_id="M100",
    amount=-100.0,
    category="Utilities",
    account="Checking (...1234)",
    account_id="A1",
    is_past=True,
    transaction_id="T1",
    due_date="2026-03-15",
    last_paid_date="2026-03-13",
    **extra,
) -> dict:
    return {
        "stream_id": stream_id,
        "merchant": merchant,
        "merchant_id": merchant_id,
        "amount": amount,
        "actual_amount": amount,
        "frequency": "monthly",
        "category": category,
        "account": account,
        "account_id": account_id,
        "is_past": is_past,
        "transaction_id": transaction_id,
        "due_date": due_date,
        "last_paid_date": last_paid_date,
        **extra,
    }


TODAY = date(2026, 3, 16)


def _assert_accountability_balances(result):
    """Assert both accountability groups sum correctly."""
    ms = result.accountability.monarch_streams
    assert (
        ms.matched_to_config
        + ms.matched_to_credit_accounts
        + ms.matched_by_bill_filter
        + ms.ignored_by_pattern
        + ms.ignored_by_merchant_list
        + ms.unclassified
    ) == ms.total

    ce = result.accountability.config_expectations
    assert ce.linked_to_monarch + ce.gap == ce.total


# =============================================================================
# Accountability
# =============================================================================


class TestAccountabilityBalances:
    def test_empty_inputs(self):
        result = build_bill_inventory(
            config=BillsConfig(),
            recurring_streams=[],
            accounts=[],
            defaults=_defaults(),
            today=TODAY,
        )
        _assert_accountability_balances(result)
        assert result.accountability.monarch_streams.total == 0
        assert result.accountability.config_expectations.total == 0

    def test_mixed_sources_all_accounted(self):
        config = BillsConfig(
            properties=[
                Property(
                    name="Home",
                    type="residence",
                    bills=[
                        PropertyBill(name="Mortgage", vendor="LoanCo", monarch_merchant_id="M1"),
                        PropertyBill(name="HOA", vendor="HOA Board", monarch_merchant_id="M2"),
                    ],
                )
            ],
            credit_accounts=[
                CreditAccount(name="Card", issuer="Bank", last4="9999", monarch_merchant_id="M3"),
            ],
            ignored_merchants=[
                IgnoredMerchant(merchant_id="M5", name="Streaming", reason="subscription_inconsequential"),
            ],
            bill_filters=BillFilterConfig(categories=["Phone"]),
        )
        streams = [
            _stream(stream_id="1", merchant_id="M1", merchant="LoanCo"),
            _stream(stream_id="2", merchant_id="M2", merchant="HOA Board"),
            _stream(stream_id="3", merchant_id="M3", merchant="Bank Card"),
            _stream(stream_id="4", merchant_id="M4", category="Same Bank Transfer"),
            _stream(stream_id="5", merchant_id="M5", merchant="Streaming"),
            _stream(stream_id="6", merchant_id="M6", category="Phone", merchant="Carrier"),
            _stream(stream_id="7", merchant_id="M7", merchant="Mystery", category="Misc"),
        ]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        ms = result.accountability.monarch_streams
        assert ms.total == 7
        assert ms.matched_to_config == 2      # M1, M2
        assert ms.matched_to_credit_accounts == 1  # M3
        assert ms.ignored_by_pattern == 1      # transfer
        assert ms.ignored_by_merchant_list == 1  # M5
        assert ms.matched_by_bill_filter == 1  # Phone
        assert ms.unclassified == 1            # Mystery

        ce = result.accountability.config_expectations
        # 3 framework slots (Mortgage+config, Electric/Gas framework-only, Water/Trash framework-only)
        # + 1 extra config (HOA) + 1 credit account = 5
        assert ce.total == 5
        assert ce.linked_to_monarch == 3  # Mortgage, HOA, Card (all have monarch_merchant_id)
        assert ce.gap == 2  # Electric/Gas, Water/Trash (framework-only, no config, no link)


class TestAccountabilityRaisesOnMismatch:
    def test_does_not_raise_on_valid_input(self):
        # Should not raise
        build_bill_inventory(
            config=BillsConfig(),
            recurring_streams=[_stream(stream_id="1", merchant_id="M1")],
            accounts=[],
            defaults=_defaults(),
            today=TODAY,
        )


# =============================================================================
# ID-Based Matching
# =============================================================================


class TestIdBasedMatching:
    def test_property_bill_matched_by_merchant_id(self):
        config = BillsConfig(
            properties=[
                Property(
                    name="Home", type="residence",
                    bills=[PropertyBill(name="Mortgage", vendor="LoanCo", monarch_merchant_id="M1")],
                )
            ]
        )
        streams = [_stream(stream_id="1", merchant_id="M1", merchant="LoanCo")]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        mortgage = next(
            i for i in result.sections.properties["Home"].items
            if i.obligation.name == "Mortgage"
        )
        assert mortgage.evidence.monarch is not None
        assert mortgage.evidence.monarch.merchant_id == "M1"
        assert mortgage.payment_status.status == "paid"

    def test_credit_account_matched_by_merchant_id(self):
        config = BillsConfig(
            credit_accounts=[
                CreditAccount(
                    name="Card", issuer="Bank", last4="9999",
                    monarch_merchant_id="M1", monarch_account_id="ACC1",
                )
            ]
        )
        streams = [_stream(stream_id="1", merchant_id="M1")]
        accts = [{"id": "ACC1", "displayName": "CARD (...9999)", "credential": {}}]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=accts,
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        assert len(result.sections.credit_accounts) == 1
        ca = result.sections.credit_accounts[0]
        assert ca.payment_status.status == "paid"

    def test_unlinked_bill_is_gap(self):
        config = BillsConfig(
            properties=[
                Property(
                    name="Home", type="residence",
                    bills=[PropertyBill(name="Mortgage", vendor="LoanCo")],  # no monarch_merchant_id
                )
            ]
        )
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        mortgage = next(
            i for i in result.sections.properties["Home"].items
            if i.obligation.name == "Mortgage"
        )
        assert mortgage.payment_status.status == "gap"

    def test_linked_merchant_not_in_streams_is_unknown(self):
        """merchant_id in config but no matching stream — merchant may be deactivated."""
        config = BillsConfig(
            properties=[
                Property(
                    name="Home", type="residence",
                    bills=[PropertyBill(name="Mortgage", vendor="LoanCo", monarch_merchant_id="M999")],
                )
            ]
        )
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        mortgage = next(
            i for i in result.sections.properties["Home"].items
            if i.obligation.name == "Mortgage"
        )
        # Has merchant_id but no stream found → unknown (not gap)
        assert mortgage.payment_status.status == "unknown"


# =============================================================================
# Multiple Streams Per Merchant
# =============================================================================


class TestMultipleStreamsPerMerchant:
    def test_all_streams_claimed(self):
        """Two streams with same merchant_id — both claimed, not double-counted."""
        config = BillsConfig(
            properties=[
                Property(
                    name="Home", type="residence",
                    bills=[PropertyBill(name="Mortgage", vendor="LoanCo", monarch_merchant_id="M1")],
                )
            ]
        )
        streams = [
            _stream(stream_id="1", merchant_id="M1", last_paid_date="2026-03-10"),
            _stream(stream_id="2", merchant_id="M1", last_paid_date="2026-03-13"),
        ]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        # Both streams claimed → 0 unclassified
        assert result.accountability.monarch_streams.unclassified == 0
        assert result.accountability.monarch_streams.matched_to_config == 2


# =============================================================================
# Stream Classification
# =============================================================================


class TestStreamClassification:
    def test_transfer_ignored_by_pattern(self):
        config = BillsConfig()
        streams = [_stream(stream_id="1", merchant_id="M1", category="Same Bank Transfer")]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)
        assert len(result.sections.ignored) == 1
        assert result.sections.ignored[0].exclusion_reason == "transfer"

    def test_income_ignored_by_pattern(self):
        config = BillsConfig()
        streams = [_stream(stream_id="1", merchant_id="M1", category="Net Pay")]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)
        assert len(result.sections.ignored) == 1
        assert result.sections.ignored[0].exclusion_reason == "income"

    def test_ignored_merchant_by_id(self):
        config = BillsConfig(
            ignored_merchants=[
                IgnoredMerchant(merchant_id="M1", name="Streaming", reason="subscription_inconsequential"),
            ]
        )
        streams = [_stream(stream_id="1", merchant_id="M1", category="Entertainment")]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)
        assert len(result.sections.ignored) == 1
        assert result.sections.ignored[0].exclusion_reason == "subscription_inconsequential"
        assert result.accountability.monarch_streams.ignored_by_merchant_list == 1

    def test_ignored_merchant_takes_precedence_over_skip_pattern(self):
        """Explicit user decision beats automatic pattern."""
        config = BillsConfig(
            ignored_merchants=[
                IgnoredMerchant(merchant_id="M1", name="Bank Thing", reason="subscription_inconsequential"),
            ]
        )
        # Category would match transfer pattern, but merchant list is checked first
        streams = [_stream(stream_id="1", merchant_id="M1", category="Same Bank Transfer")]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)
        assert result.accountability.monarch_streams.ignored_by_merchant_list == 1
        assert result.accountability.monarch_streams.ignored_by_pattern == 0

    def test_bill_filter_match_becomes_personal(self):
        config = BillsConfig(
            bill_filters=BillFilterConfig(categories=["Phone"]),
        )
        streams = [_stream(stream_id="1", merchant_id="M1", category="Phone")]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)
        assert len(result.sections.personal) == 1
        assert result.accountability.monarch_streams.matched_by_bill_filter == 1

    def test_unmatched_stream_is_unclassified(self):
        config = BillsConfig()
        streams = [_stream(stream_id="1", merchant_id="M1", category="Other")]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)
        assert len(result.sections.unclassified) == 1


# =============================================================================
# Framework Slots
# =============================================================================


class TestFrameworkSlots:
    def test_framework_gaps_when_no_config_no_monarch(self):
        config = BillsConfig(
            properties=[Property(name="Home", type="residence")]
        )
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        items = result.sections.properties["Home"].items
        assert len(items) == 3  # mortgage, electric_gas, water_trash
        for item in items:
            assert item.evidence.framework is not None
            assert item.evidence.config is None
            assert item.payment_status.status == "gap"

    def test_extra_config_bill_outside_framework(self):
        config = BillsConfig(
            properties=[
                Property(
                    name="Home", type="residence",
                    bills=[PropertyBill(name="HOA", vendor="HOA Board", monarch_merchant_id="M1")],
                )
            ]
        )
        streams = [_stream(stream_id="1", merchant_id="M1", merchant="HOA Board")]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        items = result.sections.properties["Home"].items
        hoa = next(i for i in items if i.obligation.name == "HOA")
        assert hoa.evidence.framework is None  # not a framework slot
        assert hoa.evidence.config is not None
        assert hoa.evidence.monarch is not None


# =============================================================================
# Payment Status
# =============================================================================


class TestPaymentStatus:
    def test_overdue_when_past_no_transaction(self):
        config = BillsConfig(
            properties=[
                Property(
                    name="Home", type="residence",
                    bills=[PropertyBill(name="Mortgage", vendor="LoanCo", monarch_merchant_id="M1")],
                )
            ]
        )
        streams = [_stream(stream_id="1", merchant_id="M1", is_past=True, transaction_id=None)]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        mortgage = next(
            i for i in result.sections.properties["Home"].items
            if i.obligation.name == "Mortgage"
        )
        assert mortgage.payment_status.status == "overdue"

    def test_due_soon_within_7_days(self):
        config = BillsConfig(
            bill_filters=BillFilterConfig(categories=["Phone"]),
        )
        streams = [_stream(
            stream_id="1", merchant_id="M1", category="Phone",
            is_past=False, transaction_id=None, due_date="2026-03-20",
        )]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        assert result.sections.personal[0].payment_status.status == "due_soon"


# =============================================================================
# Disconnected Accounts
# =============================================================================


class TestDisconnectedAccounts:
    def test_disconnected_by_credential(self):
        config = BillsConfig(
            credit_accounts=[
                CreditAccount(
                    name="Card", issuer="Bank", last4="1111",
                    monarch_account_id="DISC1", monarch_merchant_id="M1",
                )
            ]
        )
        streams = [_stream(stream_id="1", merchant_id="M1")]
        accts = [{"id": "DISC1", "displayName": "CARD", "credential": {"updateRequired": True}}]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=accts,
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)
        assert result.sections.credit_accounts[0].payment_status.status == "disconnected"
        assert any(a.type == "disconnected" for a in result.alerts)


# =============================================================================
# Alerts
# =============================================================================


class TestAlerts:
    def test_overdue_generates_alert(self):
        config = BillsConfig(
            bill_filters=BillFilterConfig(categories=["Phone"]),
        )
        streams = [_stream(
            stream_id="1", merchant_id="M1", category="Phone",
            is_past=True, transaction_id=None,
        )]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        assert any(a.type == "overdue" for a in result.alerts)

    def test_promo_near_expiry_generates_alert(self):
        config = BillsConfig(
            credit_accounts=[
                CreditAccount(
                    name="Store", issuer="Sync", last4="5555",
                    promos=[PromoFinancing(balance=3000.0, expires="2026-05-15")],
                )
            ]
        )
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        promo_alerts = [a for a in result.alerts if a.type == "promo_critical"]
        assert len(promo_alerts) == 1
        assert promo_alerts[0].account_last4 == "5555"


# =============================================================================
# Defaults Loading
# =============================================================================


class TestLoadDefaults:
    def test_loads_bundled_defaults(self):
        defaults = load_defaults()
        assert "residence" in defaults.property_types
        assert "rental_longterm" in defaults.property_types
        assert "rental_vacation" in defaults.property_types
        assert "land" in defaults.property_types
        assert "transfer" in defaults.skip_patterns
        assert "income" in defaults.skip_patterns

    def test_residence_has_expected_slots(self):
        defaults = load_defaults()
        slots = [s.slot for s in defaults.property_types["residence"].expected_bills]
        assert "mortgage" in slots
        assert "electric_gas" in slots
        assert "property_tax" in slots
