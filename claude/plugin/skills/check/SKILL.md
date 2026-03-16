---
name: check
description: Review bill payment status by cross-referencing your declared expectations (config) against Monarch's recurring list and transactions. Use when asked about bills, payments due, or to check on financial obligations.
---

# Check Bills Skill

Cross-reference your bill expectations (config) against Monarch's actual recurring data to find discrepancies, overdue payments, and promo deadline risks.

## Data Sources

This skill uses tools from **two MCP servers**:

**bills-mcp** (config — what you expect):
- `list_credit_accounts` — your declared credit accounts with payment methods, due days, promos
- `list_properties` — your properties and their expected bills (mortgage, water, trash, etc.)
- `list_promo_accounts` — accounts with deferred interest deadlines
- `get_bill_filters` — category patterns defining "consequential bills"
- `list_funding_accounts` — checking/savings accounts that fund bill payments

**monarch-access** (actuals — what Monarch sees):
- `list_recurring` — Monarch's detected recurring streams with last_paid_date, due_date, amount
- `list_transactions` — transaction history for deeper investigation
- `list_accounts` — account balances and sync status

## Processing Phases

### Phase 1: Load Both Sides

1. Call `list_credit_accounts`, `list_properties`, `list_promo_accounts`, `list_funding_accounts` (bills-mcp) to load expectations
2. Call `list_recurring` (monarch-access) to load actuals
3. Call `get_bill_filters` (bills-mcp) to load category filter patterns

### Phase 2: Cross-Reference

**For each expected bill in config** (credit accounts + property bills):
- Find matching recurring stream(s) by merchant name, account, or amount
- If match found: check `last_paid_date` and `is_past` for payment status
- If no match found: **flag as gap** — expected bill not appearing in Monarch

**For each recurring stream matching bill filter patterns:**
- Check if it maps to a known config entry
- If not: **flag as untracked** — Monarch sees a consequential bill not in your config

**Payment status assessment:**
- `is_past=true` + `transaction_id` present → paid this cycle
- `is_past=true` + `transaction_id=null` → **OVERDUE**
- `is_past=false` + upcoming `due_date` within 7 days → **DUE SOON**
- `last_paid_date=null` and never paid → **UNKNOWN — investigate**

**For promo accounts:**
- Calculate months until `expires`
- Required monthly = `balance / months_remaining`
- Compare to `payment_amount` — flag if insufficient
- `updated` field >30 days stale → flag for balance refresh
- <90 days until expiration → WARNING
- <30 days until expiration → CRITICAL

### Phase 3: Investigate Gaps

For items needing deeper investigation:
- Call `list_transactions` (monarch-access) to search for recent payments
- Check multiple merchant name variations
- Check if Monarch account is disconnected (`credential.updateRequired=true` in `list_accounts`)

For spouse-managed bills (`managed_by` set):
- Only check for problems (overdraft, disconnection, overdue)
- Don't flag missing config or collect detailed history
- Only include in summary if actual problem detected

### Phase 4: Summary & Triage

Present findings grouped by urgency:

1. **OVERDUE** — past due with no payment found
2. **PROMO DEADLINES** — approaching expiration (<90 days)
3. **DUE SOON** — due within 7 days, not yet paid
4. **GAPS** — expected bills not found in Monarch, or Monarch bills not in config
5. **ALL CLEAR** — count of bills verified current

For flagged items, ask user for clarification (payment method, missing config, etc.)

### Phase 5: Resolution

After user provides input:
1. Update config via bills-mcp tools (update_credit_account, register_property_bill, etc.)
2. Re-check any bills that were blocked on missing info
3. Present final status

## Disconnection Detection

Monarch accounts can silently stop syncing. Flag if:
- No transactions for an account in 30+ days
- Balance unchanged for weeks
- `credential.updateRequired=true` in account data

## Email Search

When Monarch data is insufficient, search **both configured email profiles** for:
- Statement notifications
- Payment confirmations
- Due date reminders
- Account alerts

## Payment Method Values

- `auto_draft` — Creditor pulls from bank account (mortgage)
- `auto_pay` — Bank pushes scheduled payment (bill pay)
- `auto_pay_full` — Autopay for full statement balance
- `auto_pay_min` — Autopay for minimum payment only
- `manual` — Requires manual payment each cycle

## Important Notes

- Update config incrementally as you discover info — don't wait until the end
- If a bill isn't in config but should be tracked, use register tools to add it
- If a recurring stream isn't in config, suggest adding it or adding a filter pattern
- Some credit cards may not be in Monarch (store cards, new cards) — check email
