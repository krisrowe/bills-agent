---
name: check
description: Review bill payment status by cross-referencing your declared expectations (config) against Monarch's recurring list and transactions. Use when asked about bills, payments due, or to check on financial obligations.
---

# Check Bills Skill

## Overview

This skill answers: "Are all my bills paid? Is anything falling through the cracks?"

It works by comparing two sources and showing where they agree, disagree, or have gaps.

## Key Terms — Define These for the User at the Start

Present these definitions at the beginning of every bill check, before any data:

- **Declared** — bills and accounts you told us about (your list of expected obligations)
- **Detected** — recurring payments and accounts found in your connected bank data
- **Matched** — items that are both declared AND detected (we can verify payment status)

Every section shows three groups with verifiable math:
- **Matched (N)** — declared AND detected. Full picture: your details + bank data + payment status.
- **Declared only (N)** — you told us about it but we can't find it in bank data. Can't verify payment.
- **Detected only (N)** — bank data shows it but you haven't told us about it. Needs your input.

The numbers must add up:
- Declared total = matched + declared only
- Detected total = matched + detected only

This proves nothing fell through the cracks from either source.

## Data Sources

**bills-mcp** (your list + inventory engine):
- `build_bill_inventory` — compares your list against Monarch data, caches result
- `get_inventory_section` — fetches one section at a time from cached result
- `update_credit_account` — link a credit account to its Monarch account/merchant
- `update_property_bill` — link a property bill to its Monarch merchant
- `add_ignored_merchant` — tell the system to stop asking about a Monarch stream
- `register_property_bill`, `register_credit_account` — add new items to your list
- `add_promo`, `update_promo`, `remove_promo` — manage promo financing plans
- `list_credit_accounts`, `list_properties`, etc. — inspect your list directly

**monarch-access** (what Monarch sees):
- `list_recurring` — recurring payments Monarch detected, with payment dates and amounts
- `list_accounts` — account balances and whether credentials are working
- `list_transactions` — transaction history for investigating problems
- `update_recurring` — deactivate or fix recurring payment entries in Monarch

## Phase 0: Load Data

Call these in parallel — no user interaction needed:

**From monarch-access:**
- `list_recurring` — all detected recurring payments
- `list_accounts` — all accounts with balances and credential status

Then call:
- `build_bill_inventory(recurring_streams, accounts)` — returns a manifest with:
  - `inventory_hash` — needed to fetch sections
  - `alerts` — urgent items (overdue, promo deadlines, credential problems)
  - `accountability` — coverage numbers
  - `sections` — list of available sections to fetch

## Phase 1: Present Alerts

Present alerts FIRST — these need immediate attention:

**Overdue payments** — a bill that should have been paid this cycle but wasn't.
Show: what bill, how much, when it was due, which account.

**Promo financing deadlines** — deferred interest expiring within 90 days.
For each promo, calculate:
- Months remaining = days until expiration / 30
- Required monthly payment = balance / months remaining
- Compare to current payment — flag if insufficient
- <90 days = WARNING, <30 days = CRITICAL
- Show the math so the user can see the shortfall

**Credential problems** — Monarch can't sync an account because the bank login needs refresh.
Show: which institution, which accounts are affected, what we can't verify because of it.

## Phase 2: Section-by-Section Review

Fetch each section via `get_inventory_section(section, inventory_hash)`.
Present one section at a time. After each section, offer to fix problems before moving on.

### CRITICAL PRESENTATION RULES

**The tool returns items pre-grouped.** Each section response has `matched`, `declared_only`,
and `detected_only` lists with counts. Present each group separately — never flatten into one table.

**Start every section with the coverage line:**
"You declared X. Bank detected Y. Z matched. (X = Z + declared_only ✓) (Y = Z + detected_only ✓)"

**Use ONLY these terms:** "declared", "detected", "matched". Never use: "config", "Monarch",
"gap", "accountability", "linked/unlinked", "disposition", "evidence", "monarch_merchant_id".

---

### Credit Accounts Section

Fetch `get_inventory_section("credit_accounts", hash)`. Response has pre-grouped lists.

**Section header:**
"CREDIT ACCOUNTS — You declared [declared_total]. Bank detected [detected_total].
[matched_count] matched. [declared_only_count] declared only. [detected_only_count] detected only."

**Matched ([matched_count])** — "These are both declared and detected. We can see balances
and verify payments."
| # | Account | Last4 | Balance | Day Due | Payment Method | Paid? |
- paid → "✅ Paid [date]"
- due_soon → "⚠️ Due [date]"
- overdue → "❌ Overdue since [date]"
- disconnected → "🔌 Can't verify — bank credentials need refresh"
- unknown → "❓ Can't verify"

**Declared only ([declared_only_count])** — "You told us about these but we can't find
them in your bank data. We can't verify if they've been paid. They may be vendor cards
not connected to your bank, or they need to be connected."
For each: show name, last4, issuer. If it has promos, show promo details.

**Detected only ([detected_only_count])** — "Your bank data shows these credit accounts
but you haven't told us about them. If they matter, we can add them. If not, we'll skip."
For each: show bank display name, last4, balance, institution.

**After presenting all three groups**, offer to connect declared-only items by matching
last 4 digits to detected accounts.

---

### Property Section (one per property)

Fetch `get_inventory_section("property:PropertyName", hash)`. Response has pre-grouped lists.

**Section header:**
"[PROPERTY NAME] — You declared [declared_total] bills. Bank detected [detected_total].
[matched_count] matched. [declared_only_count] declared only. [detected_only_count] detected only."

**Matched ([matched_count])** — "These bills are both declared and detected."
| # | Bill | Vendor | Amount | Day Due | Method | Paid? |

**Declared only ([declared_only_count])** — "You told us about these but we can't find
a matching recurring payment in bank data. Either it's not set up as recurring, the
merchant name doesn't match, or it's paid outside your connected accounts."
For each: show bill name, vendor, amount, method.
Note if `managed_by` is set (e.g., "👤 managed by spouse").
Note if `evidence.framework` is present (expected based on property type).

**Detected only ([detected_only_count])** — "Bank data shows these recurring payments
for this property but you haven't declared them as bills."
For each: show merchant name, amount, category, account, payment status.

**After presenting**, offer to connect declared-only items to detected recurring payments.

---

### Personal Section

Fetch `get_inventory_section("personal", hash)`. Response has pre-grouped lists.

**Section header:**
"PERSONAL BILLS — You declared [declared_total]. Bank detected [detected_total].
[matched_count] matched. [declared_only_count] declared only. [detected_only_count] detected only."

**Matched** — declared and detected. Show payment status.
**Declared only** — you told us but can't verify.
**Detected only** — bank sees recurring payments in bill-like categories (mortgage,
insurance, utilities, phone) that you haven't declared. May already be covered under
a property, or may need to be added.

---

### Ignored Section

Fetch `get_inventory_section("ignored", hash)`.

Present as a compact summary — don't list every item unless the user asks:

"We automatically skipped [N] Monarch streams:
- [X] internal bank transfers
- [Y] income (payroll, interest)
- [Z] items you previously told us to ignore (subscriptions, etc.)

These don't affect your bill status. Say the word if you want to see the full list."

---

### Unclassified Section

Fetch `get_inventory_section("unclassified", hash)`.

These are Monarch recurring payments we couldn't categorize. Present each one:

| # | Merchant | Amount | Frequency | Category | Account |

For each: "What should we do with this?"
- **"It's a bill"** → register as property bill or personal bill with merchant ID pre-linked
- **"Ignore it"** → `add_ignored_merchant(merchant_id, name, reason)`
- **"It's junk in Monarch"** → help deactivate via `update_recurring`

---

### Coverage Summary

After all sections, present a plain-language summary using the same terms:

"Across all sections: you declared [X] bills/accounts. Bank detected [Y] recurring payments.
- [A] matched (both declared and detected — we can verify these)
- [B] declared only (you told us but we can't find in bank data)
- [C] detected only (bank sees it but you haven't told us about it)
- [D] automatically skipped (internal transfers, income)
- [E] you previously told us to ignore (subscriptions, etc.)
- [F] need your input (couldn't categorize)

All [Y] bank items accounted for. All [X] declared items accounted for."

---

## Phase 3: Triage & Fix

After the section-by-section review, help fix problems that came up.

### Credential problems

For accounts where Monarch credentials need refresh:
- Tell the user which institution and which accounts are affected
- They need to log into Monarch and re-authenticate with the bank
- Next run will show live data once credentials are working

### Stale recurring payments (last paid > 4 months ago)

Don't assume it's dead. Could be:
- Paid off (loan closed, promo cleared) → remove from your list
- Merchant renamed in Monarch → find the new merchant, reconnect
- Credential disconnected → see above
- Paid outside Monarch-connected accounts → verify via email or bank statement

Search `list_transactions` for recent payments. Present what you find before taking action.

### Missing recurring payments (in your list, not in Monarch)

For bills in your list that have no Monarch match:
- Search `list_transactions` for the vendor name
- Check if the recurring payment was turned off in Monarch
- If payments exist → re-enable recurring via `update_recurring`
- If no payments found → ask user if this bill is still active

### Duplicate merchants in Monarch

When one merchant handles multiple bills (e.g., insurer with auto + home + rental policies):
1. Search `list_transactions`, group by account + amount
2. `update_transaction(id, merchant_name="New Name")` for each group
3. Set up recurring on new merchants via `update_recurring`
4. Deactivate the original merchant's recurring
5. Update your list: `update_property_bill(..., monarch_merchant_id=<new_id>)`

### Wrong categories in Monarch

If a payment has the wrong category (causing it to be skipped or miscategorized):
- Recategorize via `update_transaction` on recent transactions
- Next run will classify correctly

### Promo balance updates

For promo accounts where the balance hasn't been verified recently (>30 days):
- Check current balance from Monarch account data
- `update_promo(account_last4, promo_index, balance=..., updated=<today>)`
- Recalculate whether the payment plan clears the balance before deadline

---

## Email Search (fallback)

When Monarch data is insufficient (no recurring payment, no recent transactions),
search email for:
- Statement notifications from the vendor
- Payment confirmations
- Due date reminders

Useful for vendor cards not connected to Monarch (Best Buy, store financing, etc.).

---

## Payment Method Values

- `auto_draft` — creditor pulls from your bank account
- `auto_pay` — your bank pushes scheduled payment
- `auto_pay_full` — autopay for full statement balance
- `auto_pay_min` — autopay for minimum payment only
- `manual` — you pay manually each cycle

---

## Important Reminders

- The goal is CONFIDENCE that everything is covered, not a data dump
- Present one section at a time — don't overwhelm with everything at once
- After each section, offer to fix problems before moving on
- Use plain language — never use internal terms
- Group by source so the user can visually verify coverage
- Property type `rental` in old configs needs migration — ask if long-term or vacation
- After reconciling, rebuild the inventory to show the improved state
