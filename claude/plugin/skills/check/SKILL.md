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

First present any **ALERTS** (overdue, promo deadlines, disconnected accounts).

Then present the **complete bill inventory** organized by entity. Each entity gets a numbered
list so the user can easily see whether everything is accounted for.

**Entity types (in order):**
1. Each property from config (primary residence, each rental, etc.)
2. Credit Accounts — all credit cards, store cards, and lines of credit
3. Personal — non-property bills (phone, insurance, child support)

**For each entity, show a numbered table with columns:**

| # | Bill | Vendor | Day Due | Amount | Method | Last Paid | Status |
|---|------|--------|---------|--------|--------|-----------|--------|

Where:
- **#** — sequential number within the entity (so user can count and verify completeness)
- **Bill** — bill name from config, or merchant name from Monarch if untracked
- **Vendor** — merchant/vendor name
- **Day Due** — day of month from config `due_day` OR from Monarch `due_date` (extract day)
- **Amount** — expected from config or actual from Monarch recurring
- **Method** — payment method from config (auto_draft, auto_pay_full, manual, etc.)
- **Last Paid** — date from Monarch `last_paid_date`
- **Status** — ✅ Current, ⚠️ Due Soon, ❌ Overdue, ❓ Unknown, 🔌 Disconnected, 👤 Spouse

**For Credit Accounts specifically**, show:
- One row per account from config
- Day Due = `due_day` from config
- Amount = current balance from Monarch `list_accounts`
- Method = `payment_method` from config
- Status = based on whether autopay is configured and account is syncing

**After the inventory tables**, show:
- **GAPS** — expected bills not found in Monarch, or Monarch bills not in any entity
- **PROMO DEADLINES** — if any are within 90 days

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

## Multi-Stream Merchant Resolution

When one merchant (e.g., an insurer) handles multiple policies paid from different accounts,
Monarch creates one merchant with one recurring amount — which is wrong for all but one policy.

**Detection:** A recurring stream's amount doesn't match actual transaction amounts for that
merchant, OR transactions from the same merchant post to multiple accounts with different amounts.

**Resolution workflow** (uses monarch-access tools):

1. **Identify patterns**: Search transactions for the merchant, group by account + amount pattern
2. **Create new merchants**: Reassign transactions to descriptive names using `update_transaction`
   with a new `merchant_name` — Monarch auto-creates the merchant
3. **Set up recurring**: Use `update_recurring` or the `updateMerchant` mutation to set correct
   amount, frequency, and baseDate on each new merchant
4. **Copy logo**: Use `setMerchantLogo` to copy the original merchant's cloudinary logo ID
5. **Deactivate original**: Use `update_recurring(stream_id, status="inactive")` on the original

**Example:** "State Farm" paying auto from checking, home from joint, rental from property account
→ Split into "State Farm (Auto)", "State Farm (Home)", "State Farm (Rental)" with correct amounts.

## Stale Merchant Detection

When a recurring stream has `last_paid_date` older than 4 months or null:
- The obligation may be closed/paid off
- The merchant name may have changed (vendor acquisition, rebranding)
- The loan may have transferred to a new servicer
- The account credential may be disconnected

**Do not assume — investigate.** Search transactions for the account for similar amounts,
check for new merchants appearing around the time the old one stopped, and check account
sync status. Present findings to the user for a decision.

**Fix the source, not the filter.** If a stream is stale, guide the user to either:
- Mark it inactive via `update_recurring(stream_id, status="inactive")` (reversible)
- Remove it via `update_recurring(stream_id, status="removed")` (permanent)

Do NOT add workarounds or ignore-lists in the bills config.

## Important Notes

- Update config incrementally as you discover info — don't wait until the end
- If a bill isn't in config but should be tracked, use register tools to add it
- If a recurring stream isn't in config, suggest adding it or adding a filter pattern
- Some credit cards may not be in Monarch (store cards, new cards) — check email
