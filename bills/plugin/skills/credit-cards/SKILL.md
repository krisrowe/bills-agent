---
name: credit-cards
description: >
  Deep credit card payment verification by searching actual transaction history
  on each declared account. Bypasses Monarch's recurring stream matching — which
  breaks when autopay merchant names are generic, last paid dates are lagging,
  streams are linked to the wrong account, or credentials are disconnected. Use
  to validate /bills:check findings, to work around stream-matching issues, or
  when the user wants thorough per-card investigation with funding-side
  cross-referencing.
---

# Check Credit Cards Skill

## Overview

Verify whether credit card payments have been made by searching actual
transaction history on each card — not recurring streams. This is more
reliable than stream matching because autopay transactions have generic
merchant names that don't map to specific cards, and payment amounts vary
each month.

## Data Sources

**bills-mcp** (declared accounts):
- `list_credit_accounts` — declared credit accounts with due_day, payment_method, funding_account, promos
- `list_promo_accounts` — accounts with active 0% financing
- `list_funding_accounts` — checking/savings accounts that pay bills

**monarch-access** (live data):
- `list_accounts` — current balances, account IDs, credential status
- `list_transactions` — transaction history per account

## Phase 1: Load Data

Call these in parallel — no user interaction needed:

1. `list_credit_accounts` — get declared accounts from config
2. `list_accounts` — get Monarch accounts with current balances
3. `list_funding_accounts` — get declared checking/savings accounts

## Phase 2: Match Declared to Monarch Accounts

For each declared credit account, find the corresponding Monarch account:

- Match by `monarch_account_id` if configured
- Otherwise match by last4 digits against Monarch account `mask`
- If ambiguous (multiple matches), ask the user to clarify
- If no match found, flag as disconnected

After matching, update any unlinked accounts with `update_credit_account`
to store the `monarch_account_id` for future runs.

## Phase 3: Search Payment Transactions

For each matched account, search for recent payments:

```
list_transactions(account_id=<credit_card_account_id>, start_date=<60_days_ago>)
```

**Identify payments:** Look for positive-amount transactions on the credit
card account. These represent payments credited to the card. Common
category names include "Credit Card Payment", "Payment", "Transfer".

Pull at least the **last 2 payments** to show both current and prior cycle.

## Phase 3b: Fallback — Search Funding Side for Disconnected Accounts

When Phase 3 returns no transactions for an account due to:
- Credential `updateRequired` (⚡ disconnected)
- No Monarch account match (❌ no link)

Search from the **funding side** instead:

1. Call `list_transactions` with **no `account_ids` filter**, using `search`
   set to the institution/issuer name (e.g., "First National", "Acme Bank")
2. Try multiple search terms if the first returns nothing:
   - Issuer name (e.g., "First National", "Acme Bank")
   - Card brand or program name (e.g., "Rewards Plus", "Travel Card")
   - Account name from config
3. Results will show outgoing debits from checking/savings accounts —
   these are the payments to the disconnected card
4. Note which checking account the payment came from (useful for updating
   `funding_account` in config if not set)

This is the **primary** method for disconnected accounts, not optional.
Always attempt it before reporting "no payment found."

## Phase 4: Cross-Reference Funding Accounts

For each payment found on the credit card side, optionally identify which
checking/savings account it came from:

1. Get the payment amount and date from the card-side transaction
2. Search `list_transactions` on each declared funding account for a
   matching debit (same amount, date within +/-2 days)
3. If found, note the funding account name/mask

This step is best-effort — autopay merchants and timing offsets may prevent
exact matches. Skip if it would require too many API calls (more than 3-4
funding accounts).

## Phase 5: Present Results

Build a table with one row per declared credit account:

```
| # |    | Account                   | Balance    | Due  | Status  | Paid  | +/-         | Next | Prev 1 | $      | Prev 2 | $      | Paid From          |
|---|----|---------------------------|------------|------|---------|-------|-------------|------|--------|--------|--------|--------|--------------------|
| 1 |    | Acme Visa (1234)          | $450.00    | 9th  | Paid    | 4/7   | ✅ 2d early  | 26d  | 3/9    | $660   | 2/9    | $380   | autopay (5678)     |
| 2 |    | Big Bank MC (2345)        | $2,800.00  | 11th | Paid    | 4/11  | ✅ day of    | 28d  | 3/15   | $1,200 | 2/26   | $800   | autopay (6789)     |
| 3 |    | National Card (3456)      | $1,500.00  | 27th | Paid    | 3/29  | ⚠️ 2d late   | 14d  | 2/27   | $500   | 1/27   | $475   | autopay min (7890) |
| 4 |    | Store Card (4567)         | $3,000.00  | 10th | LATE    | —     | ❌ 3d        | 27d  | 3/15   | $110   | 2/14   | $110   | autopay (8901)     |
| 5 | ⚡ | Credit Union LOC (5678)   | $5,000.00  | 9th  | Paid    | 4/9   | ✅ day of    | 26d  | 3/9    | $125   | 2/9    | $105   | auto_draft (9012)  |
| 6 |    | Dept Store (6789)         | $0.00      | ?    | $0 bal  | —     | —           | —    | —      | —      | —      | —      | manual             |
| 7 | ❌ | Vendor Card (7890)        | ?          | ?    | No link | —     | —           | —    | —      | —      | —      | —      | manual             |
```

The second column is a **status icon** (blank when healthy):
- ⚡ = Monarch credential needs refresh (`updateRequired`) — balance/transactions may be stale
- ❌ = No Monarch account linked — can't query directly

Column definitions:
- **#** — row number
- **(icon)** — blank when healthy, ⚡ or ❌ when there's a connectivity issue
- **Account** — name and last4 from config (e.g., "Chase Amazon (0955)"). No ellipsis or dots.
- **Balance** — current balance from Monarch `list_accounts`
- **Due** — day of month from config `due_day` (e.g., "9th"). Show `?` if not configured.
- **Status** — current cycle payment status:
  - `Paid` — payment found for current billing cycle
  - `LATE` — due day has passed, no payment found
  - `$0 bal` — zero balance, no payment needed
  - `No link` — no Monarch account linked, can't verify
  - `?` — no due day configured, can't determine status
- **Paid** — date of current cycle's payment (e.g., "4/7"). `—` if not paid or unknown.
- **+/-** — timeliness relative to due date, with icon:
  - `✅ 2d early` — paid before due date
  - `✅ day of` — paid on due date
  - `⚠️ 2d late` — paid after due date
  - `❌ 3d` — days overdue (for LATE status)
  - `—` when status is unknown, $0, or no link
- **Next** — days until next cycle's due date (e.g., "26d"). `—` if no due day.
- **Prev 1** — date of previous cycle's payment
- **$** — amount of previous cycle's payment (whole dollars)
- **Prev 2** — date of the cycle before that
- **$** — amount of the cycle before that
- **Paid From** — funding account mask or payment method from config (e.g., "autopay (2653)", "manual")

### Status Indicators

After the table, flag any concerns:

**LATE** — due day has passed this month and no payment found since
the previous due date. Show: account name, due day, days overdue, last known
payment date.

**Promo deadline approaching** — account has a promo plan expiring within 90
days. Calculate:
- Months remaining = days until expiration / 30
- Required monthly payment = promo balance / months remaining
- Compare to recent payment amounts — flag if insufficient
- Show the math so the user can verify

**Disconnected account** — Monarch credentials need refresh (`updateRequired`
is true on the credential). Show: institution name, which accounts are affected,
note that balance and transactions may be stale.

**No Monarch match** — declared account has no matching Monarch account. Can't
verify anything. Ask if the account is still active or if the last4 has changed.

**Missing due day** — account doesn't have `due_day` configured. Note this and
suggest checking a recent statement email or the card issuer's website.

**Zero balance** — account has $0 balance. No payment needed — skip from
concerns. Still show in the table for completeness.

## Phase 6: Fix and Update

After presenting results, offer to fix problems:

- **Link unmatched accounts** — if a declared account wasn't matched to Monarch,
  help the user find it by searching account names or last4 digits
- **Set missing due_day** — `update_credit_account(last4, due_day=N)`
- **Update promo balances** — if a promo's `updated` date is stale (>30 days),
  update from the current Monarch balance
- **Add missing accounts** — if the user mentions a card not in config,
  `register_credit_account` to add it

## Important Notes

- Always present the table first, then flags. The table is the primary output.
- Sort by concern level: missed payments first, then promo deadlines, then
  disconnected, then clean accounts.
- This skill does NOT use recurring streams. It queries transaction history
  directly. This avoids the issues with generic autopay merchant names and
  incomplete stream coverage.
- Payments appear as positive amounts on the credit card account (credits).
  Charges appear as negative amounts (debits). Don't confuse the two.
- If `list_transactions` returns no results for an account, the account may
  be disconnected or the date range may be too narrow. Check credential status
  before assuming no payment was made.
