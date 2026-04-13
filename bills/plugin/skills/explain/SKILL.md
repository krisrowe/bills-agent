---
name: explain
description: Explain how a credit card balance got to where it is — walk through statement balance, charges, payments, and reconcile to current balance. Use when asked to explain or break down a CC balance.
---

# Bill Explain Skill

Explain how a credit card's current balance was reached by walking through statement cycles, charges, and payments.

## Input

User specifies a credit card (by name, last 4, or account). Optional: date range or statement to start from.

## Approach

### Step 1: Identify the Account

- Look up the card in Monarch (`list_accounts`) to get account ID and current balance
- If ambiguous, ask user to clarify which card

### Step 2: Pull Transactions

- Pull all transactions for the account from the relevant period (`list_transactions`)
- Default: start from the last statement balance or ~45 days back
- If user specifies a starting point (e.g., "from the Feb statement"), use that

### Step 3: Identify Key Events

Find these anchors in the transaction history:
- **Statement balance(s)** — look for the statement closing date/amount
- **Payment(s)** — large credits (negative amounts)
- **Interest charges** — finance charges

### Step 4: Segment by Date Ranges

Break the timeline into logical segments around payments and statement dates. For each segment:

1. **Starting balance** for the segment
2. **Large charges (>=$100)** — list individually with amount, merchant, and date, sorted largest first
3. **Small charges (<$100)** — summarize as count and total only
4. **Subtotals** — show count and total for large charges, count and total for small charges, and combined total
5. **Ending balance** = starting balance + charges (or - payment)

### Step 5: Reconcile

- Show final ending balance vs. current balance per Monarch
- Note any gap and likely explanation (timing, pending transactions, etc.)

## Output Format

Present each segment as a clear block:

```
**Segment N: [Date Range] — [Description]**

| # | Amount | Merchant | Date |
|---|--------|----------|------|
| 1 | $X     | Merchant | Date |
...

| | Count | Total |
|---|---|---|
| Large charges (>=$100) | N | $X |
| Small charges (<$100) | N | $X |
| All charges | N | $X |

| | |
|---|---|
| Starting balance | $X |
| + Charges (or - Payment) | $X |
| Ending balance | $X |
```

Repeat for each segment. End with:

```
**Current balance per Monarch: $X**
```

And a brief bottom-line summary of the biggest drivers.

## Notes

- Always show starting AND ending balance for every segment
- Sort large charges by amount descending within each segment
- Interest charges count as charges (not payments)
- If the math doesn't perfectly reconcile, note the gap and likely cause
- Use Monarch `list_transactions` with the account_id and appropriate date range
