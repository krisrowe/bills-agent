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
    InventoryAccountabilityError,
    SkipPatternGroup,
    build_bill_inventory,
    load_package_config,
)


# =============================================================================
# Helpers
# =============================================================================


def _defaults() -> AppDefaults:
    return AppDefaults(
        properties=[
            Property(
                name="residence",
                abstract=True,
                bills=[
                    PropertyBill(name="Mortgage"),
                    PropertyBill(name="Electric/Gas"),
                    PropertyBill(name="Water/Trash"),
                    PropertyBill(name="Property Tax"),
                ],
            ),
            Property(
                name="rental_longterm",
                abstract=True,
                bills=[
                    PropertyBill(name="Mortgage"),
                    PropertyBill(name="Insurance"),
                    PropertyBill(name="Property Tax"),
                ],
            ),
            Property(
                name="land",
                abstract=True,
                bills=[
                    PropertyBill(name="Property Tax"),
                ],
            ),
        ],
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
                    inherit="residence",
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
        # inherited: Mortgage + Electric/Gas + Water/Trash + Property Tax = 4
        # Mortgage is patched (M1 linked), HOA is extra (M2 linked)
        # Electric/Gas, Water/Trash, Property Tax = 3 gaps
        # + 1 credit account (M3 linked) = 6 total
        assert ce.total == 6
        assert ce.linked_to_monarch == 3  # Mortgage, HOA, Card
        assert ce.gap == 3  # Electric/Gas, Water/Trash, Property Tax


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
                    name="Home", inherit="residence",
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
                    name="Home", inherit="residence",
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
                    name="Home", inherit="residence",
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
                    name="Home", inherit="residence",
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
# Inheritance and Bill Resolution
# =============================================================================


class TestInheritanceAndResolution:
    def test_inherited_bills_appear_when_no_config_no_monarch(self):
        """Property inheriting from residence gets all template bills as gaps."""
        config = BillsConfig(
            properties=[Property(name="Home", inherit="residence")]
        )
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        items = result.sections.properties["Home"].items
        # residence template has 4 bills: Mortgage, Electric/Gas, Water/Trash, Property Tax
        assert len(items) == 4
        bill_names = {i.obligation.name for i in items}
        assert bill_names == {"Mortgage", "Electric/Gas", "Water/Trash", "Property Tax"}
        for item in items:
            assert item.evidence.declared is not None
            assert item.payment_status.status == "gap"

    def test_excluded_bill_does_not_appear_in_resolved_output(self):
        """A bill with deleted=True removes the inherited bill from the property."""
        config = BillsConfig(
            properties=[
                Property(
                    name="Home",
                    inherit="residence",
                    bills=[PropertyBill(name="Mortgage", deleted=True)],
                )
            ]
        )
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        items = result.sections.properties["Home"].items
        bill_names = [i.obligation.name for i in items]
        assert "Mortgage" not in bill_names
        assert "Electric/Gas" in bill_names
        assert "Property Tax" in bill_names

    def test_land_property_with_only_property_tax(self):
        """Property inheriting from land template has only Property Tax."""
        config = BillsConfig(
            properties=[Property(name="Land Parcel", inherit="land")]
        )
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        items = result.sections.properties["Land Parcel"].items
        assert len(items) == 1
        assert items[0].obligation.name == "Property Tax"

    def test_extra_bill_outside_inherited_set(self):
        """A bill not in the template is added on top of inherited bills."""
        config = BillsConfig(
            properties=[
                Property(
                    name="Home",
                    inherit="residence",
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
        assert hoa.evidence.declared is not None
        assert hoa.evidence.monarch is not None

    def test_no_inherit_uses_only_own_bills(self):
        """A concrete property with no inherit and explicit bills uses exactly those bills."""
        config = BillsConfig(
            properties=[
                Property(
                    name="Cabin",
                    bills=[
                        PropertyBill(name="Electric"),
                        PropertyBill(name="Property Tax"),
                    ],
                )
            ]
        )
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        items = result.sections.properties["Cabin"].items
        assert len(items) == 2
        bill_names = {i.obligation.name for i in items}
        assert bill_names == {"Electric", "Property Tax"}


# =============================================================================
# Resolve Inheritance
# =============================================================================


class TestResolveInheritance:
    def test_multi_level_inheritance(self):
        """A property inheriting rental_vacation gets bills from both real_estate and rental_vacation."""
        # rental_vacation inherits real_estate; real_estate has Mortgage + Property Tax
        # rental_vacation adds Electric, Water, Trash, Internet, Insurance, Management
        defaults = AppDefaults(
            properties=[
                Property(
                    name="real_estate",
                    abstract=True,
                    bills=[
                        PropertyBill(name="Mortgage"),
                        PropertyBill(name="Property Tax"),
                    ],
                ),
                Property(
                    name="rental_vacation",
                    abstract=True,
                    inherit="real_estate",
                    bills=[
                        PropertyBill(name="Electric"),
                        PropertyBill(name="Water"),
                        PropertyBill(name="Insurance"),
                    ],
                ),
            ],
            skip_patterns={},
        )
        config = BillsConfig(
            properties=[Property(name="Beach House", inherit="rental_vacation")]
        )
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=[],
            defaults=defaults, today=TODAY,
        )
        _assert_accountability_balances(result)

        items = result.sections.properties["Beach House"].items
        bill_names = {i.obligation.name for i in items}
        # Should have both real_estate bills AND rental_vacation bills
        assert "Mortgage" in bill_names
        assert "Property Tax" in bill_names
        assert "Electric" in bill_names
        assert "Water" in bill_names
        assert "Insurance" in bill_names

    def test_abstract_properties_skipped_by_inventory(self):
        """Abstract properties (templates) do not appear as property sections in inventory output."""
        config = BillsConfig(
            properties=[
                Property(
                    name="MyTemplate",
                    abstract=True,
                    bills=[PropertyBill(name="Property Tax")],
                ),
                Property(name="Real Property", inherit="MyTemplate"),
            ]
        )
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        # Abstract template should not appear as a section
        assert "MyTemplate" not in result.sections.properties
        # The concrete property should appear
        assert "Real Property" in result.sections.properties


# =============================================================================
# Exclude Behavior
# =============================================================================


class TestExcludeBehavior:
    def test_exclude_removes_inherited_bill(self):
        """A property bill marked deleted=True suppresses the inherited bill."""
        config = BillsConfig(
            properties=[
                Property(
                    name="Home",
                    inherit="residence",
                    bills=[PropertyBill(name="Mortgage", deleted=True)],
                )
            ]
        )
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        bill_names = {i.obligation.name for i in result.sections.properties["Home"].items}
        assert "Mortgage" not in bill_names
        # Other inherited bills still present
        assert "Electric/Gas" in bill_names
        assert "Property Tax" in bill_names

    def test_exclude_on_non_inherited_bill(self):
        """A locally added bill with deleted=True does not appear in resolved output."""
        config = BillsConfig(
            properties=[
                Property(
                    name="Cabin",
                    bills=[
                        PropertyBill(name="Electric"),
                        PropertyBill(name="Cable TV", deleted=True),
                    ],
                )
            ]
        )
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=[],
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        bill_names = {i.obligation.name for i in result.sections.properties["Cabin"].items}
        assert "Cable TV" not in bill_names
        assert "Electric" in bill_names


# =============================================================================
# Payment Status
# =============================================================================


class TestPaymentStatus:
    def test_overdue_when_past_no_transaction(self):
        config = BillsConfig(
            properties=[
                Property(
                    name="Home", inherit="residence",
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
# Monarch Credit Account Union
# =============================================================================


class TestMonarchCreditAccountUnion:
    def test_monarch_only_credit_account_appears_in_section(self):
        """Monarch credit account not in config shows up as unclassified."""
        config = BillsConfig()
        accts = [{"id": "ACC1", "displayName": "CARD (...9999)", "type": {"name": "credit"},
                  "subtype": {"name": "credit_card"}, "currentBalance": -500, "credential": {}}]
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=accts,
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        # Should appear in credit_accounts section
        assert len(result.sections.credit_accounts) == 1
        item = result.sections.credit_accounts[0]
        assert item.evidence.declared is None
        assert item.evidence.monarch is not None
        assert item.disposition == "unclassified"

        # Accountability
        assert result.accountability.monarch_accounts.total == 1
        assert result.accountability.monarch_accounts.not_in_config == 1

    def test_linked_credit_account_not_duplicated(self):
        """Config credit account linked to Monarch account → one item, not two."""
        config = BillsConfig(
            credit_accounts=[
                CreditAccount(name="Card", issuer="Bank", last4="9999",
                              monarch_account_id="ACC1", monarch_merchant_id="M1")
            ]
        )
        streams = [_stream(stream_id="1", merchant_id="M1")]
        accts = [{"id": "ACC1", "displayName": "CARD (...9999)", "type": {"name": "credit"},
                  "subtype": {"name": "credit_card"}, "currentBalance": -500, "credential": {}}]
        result = build_bill_inventory(
            config=config, recurring_streams=streams, accounts=accts,
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        # One item, not two
        assert len(result.sections.credit_accounts) == 1
        item = result.sections.credit_accounts[0]
        assert item.evidence.declared is not None
        assert item.evidence.monarch is not None

        # Accountability
        assert result.accountability.monarch_accounts.total == 1
        assert result.accountability.monarch_accounts.linked_to_config == 1
        assert result.accountability.monarch_accounts.not_in_config == 0

    def test_auto_match_by_last4(self):
        """Config last4 matches Monarch mask on a credit account — auto-linked."""
        config = BillsConfig(
            credit_accounts=[
                CreditAccount(name="Card", issuer="Bank", last4="9999"),  # no monarch_account_id
            ]
        )
        accts = [{"id": "ACC1", "displayName": "CARD (...9999)", "mask": "9999",
                  "type": {"name": "credit"}, "subtype": {"name": "credit_card"},
                  "currentBalance": -500, "credential": {}}]
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=accts,
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        # Should be one item with both declared and monarch evidence
        assert len(result.sections.credit_accounts) == 1
        item = result.sections.credit_accounts[0]
        assert item.evidence.declared is not None
        assert item.evidence.monarch is not None
        assert item.evidence.monarch.account_id == "ACC1"
        assert item.evidence.monarch.amount == -500

        # Monarch account should be claimed, not duplicated
        assert result.accountability.monarch_accounts.linked_to_config == 1
        assert result.accountability.monarch_accounts.not_in_config == 0

    def test_ambiguous_last4_not_auto_matched(self):
        """Two Monarch credit accounts with same mask — no auto-match."""
        config = BillsConfig(
            credit_accounts=[
                CreditAccount(name="Card", issuer="Bank", last4="9999"),
            ]
        )
        accts = [
            {"id": "ACC1", "displayName": "CARD A (...9999)", "mask": "9999",
             "type": {"name": "credit"}, "currentBalance": -500, "credential": {}},
            {"id": "ACC2", "displayName": "CARD B (...9999)", "mask": "9999",
             "type": {"name": "credit"}, "currentBalance": -200, "credential": {}},
        ]
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=accts,
            defaults=_defaults(), today=TODAY,
        )
        _assert_accountability_balances(result)

        # Config item should NOT auto-match (ambiguous)
        config_items = [i for i in result.sections.credit_accounts if i.evidence.declared is not None]
        assert len(config_items) == 1
        assert config_items[0].evidence.monarch is None  # no match

        # Both Monarch accounts should appear as unclassified
        monarch_only = [i for i in result.sections.credit_accounts if i.evidence.declared is None]
        assert len(monarch_only) == 2

    def test_non_credit_accounts_excluded(self):
        """Checking/savings accounts don't appear in credit account union."""
        config = BillsConfig()
        accts = [{"id": "ACC1", "displayName": "Checking (...1234)", "type": {"name": "depository"},
                  "subtype": {"name": "checking"}, "currentBalance": 5000, "credential": {}}]
        result = build_bill_inventory(
            config=config, recurring_streams=[], accounts=accts,
            defaults=_defaults(), today=TODAY,
        )
        assert len(result.sections.credit_accounts) == 0
        assert result.accountability.monarch_accounts.total == 0


# =============================================================================
# Package Config Loading
# =============================================================================


class TestLoadPackageConfig:
    def test_loads_bundled_config(self):
        defaults = load_package_config()
        template_names = {p.name for p in defaults.properties}
        assert "residence" in template_names
        assert "rental_longterm" in template_names
        assert "rental_vacation" in template_names
        assert "transfer" in defaults.skip_patterns
        assert "income" in defaults.skip_patterns

    def test_real_estate_templates_are_abstract(self):
        """The core real-estate templates in the package config are marked abstract."""
        defaults = load_package_config()
        template_names = {p.name for p in defaults.properties}
        abstract_names = {p.name for p in defaults.properties if p.abstract}
        for name in ("real_estate", "residence", "rental_longterm", "rental_vacation"):
            assert name in template_names, f"Expected '{name}' in package config"
            assert name in abstract_names, f"Expected '{name}' to be abstract"

    def test_residence_has_mortgage_and_utilities(self):
        defaults = load_package_config()
        residence = next(p for p in defaults.properties if p.name == "residence")
        # residence inherits from real_estate (which has Mortgage + Property Tax)
        # and adds Electric/Gas, Water/Trash, Internet, Home Insurance
        bill_names = {b.name for b in residence.bills}
        assert "Electric/Gas" in bill_names
        assert "Mortgage" not in bill_names  # mortgage is in real_estate, not re-declared in residence
