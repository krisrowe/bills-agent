"""Bill inventory: cross-reference config expectations against Monarch actuals.

Matching is deterministic by ID — no fuzzy logic. Links between config entries
and Monarch entities are persisted in config during reconciliation.

Every item from every source (framework templates, config declarations,
Monarch recurring streams) appears exactly once in the output. Nothing
is silently dropped.
"""

from __future__ import annotations

from datetime import date, timedelta
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from .config import BillsConfig


# =============================================================================
# App Defaults (loaded from defaults.yaml)
# =============================================================================


from .config import Property, PropertyBill


class SkipPatternGroup(BaseModel):
    category_patterns: list[str] = Field(default_factory=list)


class AppDefaults(BaseModel):
    properties: list[Property] = Field(default_factory=list)
    skip_patterns: dict[str, SkipPatternGroup] = Field(default_factory=dict)


def load_package_config() -> AppDefaults:
    """Load the package-level config (abstract templates, skip patterns)."""
    defaults_path = Path(__file__).parent / "config.yaml"
    with open(defaults_path) as f:
        data = yaml.safe_load(f) or {}
    return AppDefaults.model_validate(data)


def resolve_bills(prop: Property, all_properties: list[Property]) -> list[PropertyBill]:
    """Resolve a property's full bill list by applying inheritance and overrides.

    1. If prop.inherit is set, recursively resolve the parent's bills
    2. Merge prop.bills on top: match by name patches, unmatched adds
    3. Bills with deleted=True are removed
    """
    # Start with inherited bills
    inherited: list[PropertyBill] = []
    if prop.inherit:
        parent = next((p for p in all_properties if p.name == prop.inherit), None)
        if parent:
            inherited = resolve_bills(parent, all_properties)

    # Build name-indexed copy of inherited bills
    merged: dict[str, PropertyBill] = {b.name.lower(): b.model_copy() for b in inherited}

    # Apply this property's bills on top
    for bill in prop.bills:
        key = bill.name.lower()
        if key in merged:
            # Patch: only override fields that are explicitly set
            existing = merged[key]
            if bill.deleted:
                del merged[key]
                continue
            if bill.vendor is not None:
                existing.vendor = bill.vendor
            if bill.monarch_merchant_id is not None:
                existing.monarch_merchant_id = bill.monarch_merchant_id
            if bill.due_day is not None:
                existing.due_day = bill.due_day
            if bill.amount is not None:
                existing.amount = bill.amount
            if bill.payment_method is not None:
                existing.payment_method = bill.payment_method
            if bill.funding_account is not None:
                existing.funding_account = bill.funding_account
            if bill.managed_by is not None:
                existing.managed_by = bill.managed_by
            if bill.notes is not None:
                existing.notes = bill.notes
        else:
            if not bill.deleted:
                merged[key] = bill.model_copy()

    return list(merged.values())


# =============================================================================
# Inventory Data Model
# =============================================================================


class Obligation(BaseModel):
    name: str
    section: str  # credit_account, property, ignored, unidentified
    property: Optional[str] = None
    bill_type: Optional[str] = None


class DeclaredEvidence(BaseModel):
    """Evidence that this bill was declared — inherited from a template, explicitly configured, or both."""
    vendor: Optional[str] = None
    monarch_merchant_id: Optional[str] = None
    due_day: Optional[int] = None
    amount: Optional[float] = None
    payment_method: Optional[str] = None
    funding_account: Optional[str] = None
    managed_by: Optional[str] = None


class MonarchEvidence(BaseModel):
    stream_id: Optional[str] = None
    merchant_id: Optional[str] = None
    amount: Optional[float] = None
    actual_amount: Optional[float] = None
    frequency: Optional[str] = None
    category: Optional[str] = None
    account: Optional[str] = None
    account_id: Optional[str] = None


class Evidence(BaseModel):
    declared: Optional[DeclaredEvidence] = None
    monarch: Optional[MonarchEvidence] = None


class PaymentStatus(BaseModel):
    status: str  # paid, due_soon, overdue, gap, disconnected, unknown
    last_paid: Optional[str] = None
    due_date: Optional[str] = None
    transaction_id: Optional[str] = None


class BillItem(BaseModel):
    obligation: Obligation
    evidence: Evidence
    disposition: str  # tracked, ignored, unidentified, unclassified
    exclusion_reason: Optional[str] = None
    payment_status: Optional[PaymentStatus] = None


class Alert(BaseModel):
    type: str  # overdue, promo_critical, disconnected, gap
    item: Optional[BillItem] = None
    account_last4: Optional[str] = None
    balance: Optional[float] = None
    expires: Optional[str] = None
    required_monthly: Optional[float] = None
    account: Optional[str] = None


class DeclaredBillsSummary(BaseModel):
    """Per-property declared bill counts."""
    property_name: str
    inherits: Optional[str] = None
    declared: int = 0
    linked: int = 0
    unlinked: int = 0


class StreamAccountingSummary(BaseModel):
    """Per-property linked stream counts + skip/ignore/unidentified."""
    total: int = 0
    linked_per_property: dict[str, int] = Field(default_factory=dict)
    skipped_transfers: list[str] = Field(default_factory=list)
    skipped_income: list[str] = Field(default_factory=list)
    ignored_by_you: list[str] = Field(default_factory=list)
    unidentified_count: int = 0
    unidentified_preview: list[str] = Field(default_factory=list)


class PropertySection(BaseModel):
    type: str
    items: list[BillItem] = Field(default_factory=list)


class InventorySections(BaseModel):
    credit_accounts: list[BillItem] = Field(default_factory=list)
    properties: dict[str, PropertySection] = Field(default_factory=dict)
    ignored: list[BillItem] = Field(default_factory=list)
    unidentified: list[BillItem] = Field(default_factory=list)


class InventoryWarning(BaseModel):
    type: str  # unrecognized_property_type, etc.
    property: Optional[str] = None
    message: str


class BillInventory(BaseModel):
    declared_summary: list[DeclaredBillsSummary] = Field(default_factory=list)
    stream_accounting: StreamAccountingSummary = Field(default_factory=StreamAccountingSummary)
    alerts: list[Alert] = Field(default_factory=list)
    warnings: list[InventoryWarning] = Field(default_factory=list)
    sections: InventorySections = Field(default_factory=InventorySections)


# =============================================================================
# Helpers
# =============================================================================


def _matches_skip_patterns(
    category: str, skip_patterns: dict[str, SkipPatternGroup]
) -> Optional[str]:
    """Check if category matches any skip pattern group. Returns reason or None."""
    if not category:
        return None
    lower_cat = category.lower()
    for reason, group in skip_patterns.items():
        for pattern in group.category_patterns:
            if fnmatch(lower_cat, pattern.lower()):
                return reason
    return None



def _monarch_evidence_from_stream(stream: dict) -> MonarchEvidence:
    """Build MonarchEvidence from a recurring stream dict."""
    return MonarchEvidence(
        stream_id=str(stream.get("stream_id", "")) or None,
        merchant_id=str(stream.get("merchant_id", "")) or None,
        amount=stream.get("amount"),
        actual_amount=stream.get("actual_amount"),
        frequency=stream.get("frequency"),
        category=stream.get("category"),
        account=stream.get("account"),
        account_id=str(stream.get("account_id", "")) or None,
    )


def _compute_payment_status(stream: dict, today: date) -> PaymentStatus:
    """Compute payment status from a Monarch recurring stream."""
    is_past = stream.get("is_past", False)
    transaction_id = stream.get("transaction_id")
    due_date_str = stream.get("due_date")
    last_paid_str = stream.get("last_paid_date")

    if is_past and transaction_id:
        return PaymentStatus(
            status="paid",
            last_paid=last_paid_str,
            due_date=due_date_str,
            transaction_id=str(transaction_id),
        )

    if is_past and not transaction_id:
        return PaymentStatus(
            status="overdue",
            due_date=due_date_str,
            last_paid=last_paid_str,
        )

    if due_date_str:
        try:
            due = date.fromisoformat(due_date_str)
            if due - today <= timedelta(days=7):
                return PaymentStatus(
                    status="due_soon",
                    due_date=due_date_str,
                    last_paid=last_paid_str,
                )
        except ValueError:
            pass

    return PaymentStatus(
        status="unknown",
        due_date=due_date_str,
        last_paid=last_paid_str,
    )


def _best_stream(streams: list[dict]) -> dict:
    """Pick the best stream from a list sharing the same merchant_id.

    Prefers the one with the most recent last_paid_date.
    """
    if len(streams) == 1:
        return streams[0]
    return max(streams, key=lambda s: s.get("last_paid_date") or "")


def _build_streams_by_merchant(
    recurring_streams: list[dict],
) -> dict[str, list[dict]]:
    """Index streams by merchant_id for fast lookup."""
    by_merchant: dict[str, list[dict]] = {}
    for stream in recurring_streams:
        mid = str(stream.get("merchant_id", ""))
        if mid:
            by_merchant.setdefault(mid, []).append(stream)
    return by_merchant


# =============================================================================
# Build Inventory
# =============================================================================


def build_bill_inventory(
    config: BillsConfig,
    recurring_streams: list[dict],
    accounts: list[dict],
    defaults: AppDefaults,
    today: Optional[date] = None,
) -> BillInventory:
    """Build complete bill inventory from config + Monarch data.

    Matching is deterministic by ID. No fuzzy logic. Every framework slot,
    config entry, and Monarch stream appears exactly once in the output.
    """
    if today is None:
        today = date.today()

    items: list[BillItem] = []
    warnings: list[InventoryWarning] = []
    claimed_stream_ids: set[str] = set()
    streams_by_merchant = _build_streams_by_merchant(recurring_streams)

    # Build disconnected account set
    disconnected_account_ids: set[str] = set()
    for acct in accounts:
        cred = acct.get("credential") or {}
        if cred.get("updateRequired"):
            acct_id = str(acct.get("id", ""))
            if acct_id:
                disconnected_account_ids.add(acct_id)

    # Build ignored merchant lookup
    ignored_merchant_ids: dict[str, str] = {
        m.merchant_id: m.reason for m in config.ignored_merchants
    }

    def _claim_streams_for_merchant(merchant_id: str) -> tuple[list[dict], set[str]]:
        """Claim all streams for a merchant_id. Returns (streams, stream_ids)."""
        matched = streams_by_merchant.get(merchant_id, [])
        ids = set()
        for s in matched:
            sid = str(s.get("stream_id", ""))
            if sid and sid not in claimed_stream_ids:
                ids.add(sid)
        return matched, ids

    def _payment_status_for_merchant(
        merchant_id: Optional[str],
    ) -> tuple[Optional[PaymentStatus], Optional[MonarchEvidence]]:
        """Look up payment status and evidence by merchant_id."""
        if not merchant_id:
            return PaymentStatus(status="gap"), None

        matched, new_ids = _claim_streams_for_merchant(merchant_id)
        # Only use unclaimed streams
        unclaimed = [s for s in matched if str(s.get("stream_id", "")) in new_ids]

        if not unclaimed:
            # merchant_id exists in config but no streams found
            return PaymentStatus(status="unknown"), None

        claimed_stream_ids.update(new_ids)
        best = _best_stream(unclaimed)
        evidence = _monarch_evidence_from_stream(best)

        acct_id = str(best.get("account_id", ""))
        if acct_id in disconnected_account_ids:
            return PaymentStatus(status="disconnected"), evidence

        return _compute_payment_status(best, today), evidence

    # Track which Monarch account IDs are claimed by config credit accounts
    claimed_monarch_account_ids: set[str] = set()

    # Build last4-to-Monarch-credit-account index for auto-matching
    monarch_credit_by_mask: dict[str, list[dict]] = {}
    for acct in accounts:
        acct_type = (acct.get("type") or {}).get("name", "")
        if acct_type != "credit":
            continue
        mask = acct.get("mask", "")
        if mask:
            monarch_credit_by_mask.setdefault(mask, []).append(acct)

    # ------------------------------------------------------------------
    # Step 1+2: Resolve bills per property via inheritance, match by ID
    # ------------------------------------------------------------------

    # Combine defaults + config properties for inheritance resolution
    all_properties = defaults.properties + config.properties

    # Per-property stream counts for stream_accounting
    streams_linked_per_property: dict[str, int] = {}

    for prop in config.properties:
        if prop.abstract:
            continue

        # Resolve full bill list through inheritance chain
        resolved = resolve_bills(prop, all_properties)

        if not resolved and prop.inherit:
            parent = next((p for p in all_properties if p.name == prop.inherit), None)
            if parent is None:
                warnings.append(InventoryWarning(
                    type="unresolved_inherit",
                    property=prop.name,
                    message=f"Property inherits from '{prop.inherit}' but no template "
                    f"with that name was found.",
                ))

        for bill in resolved:
            merchant_id = bill.monarch_merchant_id
            payment, monarch_ev = _payment_status_for_merchant(merchant_id)

            if merchant_id and monarch_ev:
                matched = streams_by_merchant.get(merchant_id, [])
                count = sum(
                    1 for s in matched
                    if str(s.get("stream_id", "")) in claimed_stream_ids
                )
                streams_linked_per_property[prop.name] = (
                    streams_linked_per_property.get(prop.name, 0) + count
                )

            item = BillItem(
                obligation=Obligation(
                    name=bill.name,
                    section="property",
                    property=prop.name,
                ),
                evidence=Evidence(
                    declared=DeclaredEvidence(
                        vendor=bill.vendor,
                        monarch_merchant_id=bill.monarch_merchant_id,
                        due_day=bill.due_day,
                        amount=bill.amount,
                        payment_method=bill.payment_method,
                        funding_account=bill.funding_account,
                        managed_by=bill.managed_by,
                    ),
                    monarch=monarch_ev,
                ),
                disposition="tracked",
                payment_status=payment,
            )
            items.append(item)

    # ------------------------------------------------------------------
    # Step 3: Config credit accounts
    # ------------------------------------------------------------------

    streams_linked_credit = 0

    for ca in config.credit_accounts:
        # Payment stream by monarch_merchant_id
        merchant_id = ca.monarch_merchant_id
        payment, monarch_ev = _payment_status_for_merchant(merchant_id)

        if merchant_id and monarch_ev:
            matched = streams_by_merchant.get(merchant_id, [])
            count = sum(
                1 for s in matched
                if str(s.get("stream_id", "")) in claimed_stream_ids
            )
            streams_linked_credit += count

        # Account info by monarch_account_id, with last4 auto-match fallback
        monarch_acct = None
        matched_account_id = ca.monarch_account_id

        if matched_account_id:
            # Explicit ID link
            for acct in accounts:
                if str(acct.get("id", "")) == matched_account_id:
                    monarch_acct = acct
                    break
        elif ca.last4:
            # Auto-match by last4/mask on credit-type accounts
            candidates = monarch_credit_by_mask.get(ca.last4, [])
            if len(candidates) == 1:
                monarch_acct = candidates[0]
                matched_account_id = str(monarch_acct.get("id", ""))

        if matched_account_id:
            claimed_monarch_account_ids.add(matched_account_id)

        # Override payment status if account is disconnected
        if matched_account_id and matched_account_id in disconnected_account_ids:
            payment = PaymentStatus(status="disconnected")

        # Build monarch evidence — prefer stream evidence, supplement with account
        if monarch_ev is None and monarch_acct:
            monarch_ev = MonarchEvidence(
                account=monarch_acct.get("displayName"),
                account_id=str(monarch_acct.get("id", "")),
                amount=monarch_acct.get("currentBalance"),
            )

        item = BillItem(
            obligation=Obligation(
                name=ca.name,
                section="credit_account",
            ),
            evidence=Evidence(
                declared=DeclaredEvidence(
                    monarch_merchant_id=ca.monarch_merchant_id,
                    due_day=ca.due_day,
                    payment_method=ca.payment_method,
                    funding_account=ca.funding_account,
                ),
                monarch=monarch_ev,
            ),
            disposition="tracked",
            payment_status=payment,
        )
        items.append(item)

    # ------------------------------------------------------------------
    # Step 3b: Monarch credit accounts not in config
    # ------------------------------------------------------------------

    for acct in accounts:
        acct_type = (acct.get("type") or {}).get("name", "")
        if acct_type != "credit":
            continue
        acct_id = str(acct.get("id", ""))
        if acct_id in claimed_monarch_account_ids:
            continue

        # This Monarch credit account has no config entry
        display = acct.get("displayName", "Unknown")
        balance = acct.get("currentBalance")

        disconnected = acct_id in disconnected_account_ids
        ps = PaymentStatus(status="disconnected") if disconnected else PaymentStatus(status="unknown")

        items.append(BillItem(
            obligation=Obligation(
                name=display,
                section="credit_account",
            ),
            evidence=Evidence(
                monarch=MonarchEvidence(
                    account=display,
                    account_id=acct_id,
                    amount=balance,
                ),
            ),
            disposition="unclassified",
            payment_status=ps,
        ))

    # ------------------------------------------------------------------
    # Step 4: Classify remaining Monarch streams
    # ------------------------------------------------------------------

    skipped_transfers: list[str] = []
    skipped_income: list[str] = []
    ignored_by_you: list[str] = []
    unidentified_count = 0
    unidentified_preview: list[str] = []

    for stream in recurring_streams:
        sid = str(stream.get("stream_id", ""))
        if sid in claimed_stream_ids:
            continue

        merchant_id = str(stream.get("merchant_id", ""))
        category = stream.get("category", "")
        merchant_name = stream.get("merchant") or "Unknown"

        # 1. Check ignored_merchants by merchant_id
        if merchant_id in ignored_merchant_ids:
            claimed_stream_ids.add(sid)
            reason = ignored_merchant_ids[merchant_id]
            ignored_by_you.append(merchant_name)
            items.append(BillItem(
                obligation=Obligation(name=merchant_name, section="ignored"),
                evidence=Evidence(monarch=_monarch_evidence_from_stream(stream)),
                disposition="ignored",
                exclusion_reason=reason,
            ))
            continue

        # 2. Check skip_patterns by category
        skip_reason = _matches_skip_patterns(category, defaults.skip_patterns)
        if skip_reason:
            claimed_stream_ids.add(sid)
            if skip_reason == "transfer":
                skipped_transfers.append(merchant_name)
            else:
                skipped_income.append(merchant_name)
            items.append(BillItem(
                obligation=Obligation(name=merchant_name, section="ignored"),
                evidence=Evidence(monarch=_monarch_evidence_from_stream(stream)),
                disposition="ignored",
                exclusion_reason=skip_reason,
            ))
            continue

        # 3. Unidentified — not linked to any declared bill
        claimed_stream_ids.add(sid)
        unidentified_count += 1
        amount = stream.get("amount")
        amount_str = f" (${abs(amount):.0f})" if amount is not None else ""
        if len(unidentified_preview) < 10:
            unidentified_preview.append(f"{merchant_name}{amount_str}")
        items.append(BillItem(
            obligation=Obligation(name=merchant_name, section="unidentified"),
            evidence=Evidence(monarch=_monarch_evidence_from_stream(stream)),
            disposition="unclassified",
            payment_status=_compute_payment_status(stream, today),
        ))

    # ------------------------------------------------------------------
    # Step 5: Alerts
    # ------------------------------------------------------------------

    alerts: list[Alert] = []
    for item in items:
        if item.disposition != "tracked":
            continue
        ps = item.payment_status
        if ps and ps.status == "overdue":
            alerts.append(Alert(type="overdue", item=item))
        if ps and ps.status == "disconnected":
            alerts.append(Alert(type="disconnected", account=item.obligation.name, item=item))

    # Promo alerts
    for ca in config.credit_accounts:
        for promo in ca.promos:
            if not promo.expires:
                continue
            try:
                exp = date.fromisoformat(promo.expires)
            except ValueError:
                continue
            days_left = (exp - today).days
            if days_left <= 90:
                months_left = max(days_left / 30.0, 0.1)
                required = promo.balance / months_left
                alerts.append(Alert(
                    type="promo_critical",
                    account_last4=ca.last4,
                    balance=promo.balance,
                    expires=promo.expires,
                    required_monthly=round(required, 2),
                ))

    # ------------------------------------------------------------------
    # Step 6: Verify stream balance
    # ------------------------------------------------------------------

    total_streams = len(recurring_streams)
    linked_count = sum(streams_linked_per_property.values()) + streams_linked_credit
    skipped_count = len(skipped_transfers) + len(skipped_income)
    ignored_count = len(ignored_by_you)
    accounted = linked_count + skipped_count + ignored_count + unidentified_count

    if accounted != total_streams:
        # Sanity check — should not happen under normal conditions
        warnings.append(InventoryWarning(
            type="stream_balance_mismatch",
            message=(
                f"Stream totals don't add up: linked={linked_count}, "
                f"skipped={skipped_count}, ignored={ignored_count}, "
                f"unidentified={unidentified_count}, total={total_streams}"
            ),
        ))

    # ------------------------------------------------------------------
    # Step 7: Organize into sections
    # ------------------------------------------------------------------

    sections = InventorySections()
    for item in items:
        sec = item.obligation.section
        if sec == "credit_account":
            sections.credit_accounts.append(item)
        elif sec == "property":
            prop_name = item.obligation.property or "Unknown"
            if prop_name not in sections.properties:
                prop_type = "unknown"
                for p in config.properties:
                    if p.name == prop_name:
                        prop_type = p.inherit or "unknown"
                        break
                sections.properties[prop_name] = PropertySection(type=prop_type)
            sections.properties[prop_name].items.append(item)
        elif sec == "ignored":
            sections.ignored.append(item)
        elif sec == "unidentified":
            sections.unidentified.append(item)

    # ------------------------------------------------------------------
    # Step 8: Build declared_summary and stream_accounting
    # ------------------------------------------------------------------

    declared_summary: list[DeclaredBillsSummary] = []

    # Credit accounts row
    ca_linked = sum(
        1 for i in sections.credit_accounts
        if i.evidence.declared and i.evidence.monarch
    )
    ca_unlinked = sum(
        1 for i in sections.credit_accounts
        if i.evidence.declared and not i.evidence.monarch
    )
    ca_declared = ca_linked + ca_unlinked
    if ca_declared > 0 or sections.credit_accounts:
        declared_summary.append(DeclaredBillsSummary(
            property_name="Credit Accounts",
            declared=ca_declared,
            linked=ca_linked,
            unlinked=ca_unlinked,
        ))

    # One row per concrete property
    for prop in config.properties:
        if prop.abstract:
            continue
        prop_items = sections.properties.get(prop.name, PropertySection(type="")).items
        p_linked = sum(1 for i in prop_items if i.evidence.monarch)
        p_unlinked = sum(1 for i in prop_items if not i.evidence.monarch)
        declared_summary.append(DeclaredBillsSummary(
            property_name=prop.name,
            inherits=prop.inherit,
            declared=len(prop_items),
            linked=p_linked,
            unlinked=p_unlinked,
        ))

    stream_accounting = StreamAccountingSummary(
        total=total_streams,
        linked_per_property={
            **streams_linked_per_property,
            **({"Credit Accounts": streams_linked_credit} if streams_linked_credit else {}),
        },
        skipped_transfers=skipped_transfers,
        skipped_income=skipped_income,
        ignored_by_you=ignored_by_you,
        unidentified_count=unidentified_count,
        unidentified_preview=unidentified_preview,
    )

    return BillInventory(
        declared_summary=declared_summary,
        stream_accounting=stream_accounting,
        alerts=alerts,
        warnings=warnings,
        sections=sections,
    )
