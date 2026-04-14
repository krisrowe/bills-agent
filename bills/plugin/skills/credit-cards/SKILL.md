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

Query all matched card accounts for payments in a single call:

```
list_transactions(
    account_ids=[<all_matched_card_account_ids>],
    start_date=<60_days_ago>,
    is_expense=false
)
```

`is_expense=false` returns only positive-amount transactions — payments
received on the card, refunds, credits. No charges. This dramatically
reduces the response size and avoids the problem of charges pushing
payments out of the result window on high-volume cards.

From the results, group payments by account and identify the last 2-3
payments per card to populate the table's Last Due and Prior Due columns.

**Autopay preemption:** For `auto_pay_full` accounts, check for ANY payment
on the card between the previous due date and the current due date. If a
large manual payment earlier in the cycle already satisfied the balance,
autopay legitimately won't fire. Only flag as missing if NO payment of
any kind was found in that cycle window.

## Phase 3b: Fallback — Search Funding Side for Disconnected Accounts

When Phase 3 returns no transactions for an account due to:
- Credential `updateRequired` (🔌 disconnected)
- No Monarch account match (❌ no link)

Search from the **funding side** instead:

1. Call `list_transactions` with **no `account_ids` filter**, `is_expense=true`,
   and `search` set to the institution/issuer name (e.g., "First National", "Acme Bank")
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

Build a table with one row per declared credit account, **sorted by priority**:

1. ❌ LATE — overdue, needs immediate action
2. ⏰ DUE — due soon, needs attention
3. ✅ Paid — sorted by Next due ascending (soonest first)
4. ? / No link — unknown status, can't verify
5. $0 bal — no action needed, bottom of table

```
| # |    | Account              | Balance    | Due  | Status    | Next | Last Due   | Paid | $      | Prior Due  | Paid | $      | Paid From         |
|---|----|----------------------|------------|------|-----------|------|------------|------|--------|------------|------|--------|-------------------|
| 1 |    | BigBox Store (5678)  | $4,200.00  | 10th | ⏰ DUE    | 1d   | ✅ 3/10    | 3/10 | $150   | ❌ 2/10    | —    | $0*    | manual (4321)     |
| 2 |    | Travel Card (9012)   | $800.00    | 1st  | ✅ Paid   | 18d  | ✅ 4/1     | 3/20 | $3,500 | ✅ 3/1     | 2/25 | $2,800 | autopay (4321)    |
| 3 |    | Rewards Plus (3456)  | $337.00    | 26th | ✅ Paid   | 13d  | ✅ 3/26    | 3/26 | $25    | ✅ 2/26    | 2/26 | $25    | manual (9876)     |
| 4 |    | Acme Visa (1234)     | $2,500.00  | 15th | ✅ Paid   | 22d  | ✅ 3/15    | 3/15 | $1,200 | ✅ 2/15    | 2/14 | $980   | autopay (9876)    |
| 5 | 🔌 | Old HELOC (2468)     | $5,000.00  | 9th  | ✅ Paid   | 26d  | ✅ 4/9     | 4/9  | $105   | ✅ 3/9     | 3/9  | $124   | auto_draft (5555) |
| 6 |    | Promo Card (7890)    | $6,444.00  | ?    | ?         | —    | —          | 3/31 | $110   | —          | 3/17 | $110   | manual (4321)     |
| 7 | ❌ | Spouse Card (2468)   | ?          | ?    | No link   | —    | —          | 4/8  | $107   | —          | 3/25 | $107   | manual            |
| 8 |    | Dept Store (1357)    | $0.00      | ?    | $0 bal    | —    | —          | —    | —      | —          | —    | —      | manual            |
```

*\* BigBox Store 2/10: payment posted then reversed — net $0*

The second column is a **connectivity icon** (blank when healthy):
- 🔌 = Monarch credential disconnected (`updateRequired`) — balance/transactions may be stale
- ❌ = No Monarch account linked — can't query directly

Column definitions:
- **#** — row number
- **(icon)** — blank when healthy, 🔌 or ❌ when there's a connectivity issue
- **Account** — name and last4 from config (e.g., "Acme Visa (1234)"). No ellipsis or dots.
- **Balance** — current balance from Monarch `list_accounts`
- **Due** — day of month from config `due_day` (e.g., "15th"). Show `?` if not configured.
- **Status** — current cycle payment status. Only these values:
  - `✅ Paid` — current cycle is satisfied
  - `⏰ DUE` — due within 7 days or today, no payment yet
  - `❌ LATE` — due date has passed, no payment found
  - `$0 bal` — zero balance, no payment needed
  - `?` — no due day configured, can't determine
  - `No link` — no Monarch account linked, can't verify
- **Next** — days until next cycle's due date (e.g., "22d"). `—` if no due day.
- **Last Due** — most recent due date strictly before today. Prefixed with status icon:
  - ✅ payment found on or before due date
  - ⚠️ payment found but after due date (paid late)
  - ❌ no payment found or payment reversed
- **Paid** — date the payment posted for that cycle. `—` if none found.
- **$** — payment amount (whole dollars)
- **Prior Due** — the due date before Last Due, same icon treatment
- **Paid** — date the payment posted for the prior cycle
- **$** — payment amount (whole dollars)
- **Paid From** — funding account mask or payment method from config

### After the Table — Two Separate Lists

Present concerns in two clearly separated lists:

**1. Payment actions needed** — things requiring user action NOW:

- **❌ LATE payments** — due date has passed, no payment found. Show: account
  name, due day, days overdue, last known payment date.
- **⏰ Payments due soon** — due within 7 days with no payment yet. Show:
  account name, due date, days remaining, expected amount.
- **Promo deadline approaching** — account has a promo plan expiring within 90
  days. Calculate:
  - Months remaining = days until expiration / 30
  - Required monthly payment = promo balance / months remaining
  - Compare to recent payment amounts — flag if insufficient
  - Show the math so the user can verify
- **Reversed/failed payments** — payment posted then reversed, returned check
  fees, etc.

**2. Config & hygiene items** — maintenance tasks, not urgent:

- **🔌 Disconnected credentials** — Monarch credentials need refresh. Show:
  institution name, which accounts are affected.
- **Missing due_day** — accounts with a balance but no `due_day` configured.
  Suggest checking a recent statement email or issuer website.
- **No Monarch match** — declared account not found in Monarch. Ask if still
  active or if last4 has changed.
- **Stale promo balances** — promo `updated` date >30 days old. Offer to
  refresh from current Monarch balance.
- **Zero balance accounts** — may be closed or inactive. Ask if they should
  be removed from config.
- **Missing funding accounts** — payment found but can't identify which
  checking account it came from.

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
