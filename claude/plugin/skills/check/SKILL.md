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

Then present the **complete bill inventory** in three sections.

---

**SECTION 1: Credit Accounts**

All credit cards, store cards, and lines of credit (NOT mortgages — those go under properties).
One row per account from config. Numbered sequentially.

| # | Account | Last4 | Issuer | Day Due | Balance | Method | Status |
|---|---------|-------|--------|---------|---------|--------|--------|

- **Day Due** — from config `due_day`
- **Balance** — current balance from Monarch `list_accounts`
- **Method** — `auto_pay_full`, `auto_pay_min`, `manual` from config
- **Status** — ✅ Current, ⚠️ Due Soon, ❌ Overdue, 🔌 Disconnected

Flag any promo accounts with deadline info beneath the table.

---

**SECTION 2: Properties**

One sub-section per property from config. For each property, show a **statically numbered**
list of every bill that should exist for that property type.

**Expected bills by property type:**

Residence: (1) Mortgage, (2) Electric/Gas, (3) Water/Trash, (4) Internet, (5) Home Insurance,
(6) Property Tax, plus any additional (HELOC, HOA, etc.)

Active rental: (1) Mortgage, (2) Electric, (3) Water, (4) Trash, (5) Internet, (6) Insurance,
(7) Property Tax, (8) Management fees, plus any additional

Land-only (no structure, no tenants): (1) Property Tax only

The static numbering is the **expected minimum**. Every property should have these. If a bill
for a static number is missing from both config AND Monarch, show it as a gap row:

| # | Bill | Vendor | Day Due | Amount | Method | Last Paid | Status |
|---|------|--------|---------|--------|--------|-----------|--------|
| 1 | Mortgage | Vendor | 1 | $X | auto_draft | 3/2 | ✅ |
| 2 | Electric | — | — | — | — | — | ❓ NOT TRACKED |
| 3 | Water | — | — | — | — | — | ❓ NOT TRACKED |

If Monarch shows additional bills not in the static list (e.g., a second electric provider),
add them with an **ad-hoc letter suffix** to highlight they're discovered but not declared:

| 4a | Starlink (discovered) | Starlink | 10 | $120 | — | 3/10 | ⚠️ NOT IN CONFIG |

This makes it visually obvious what's expected vs what's discovered vs what's missing.

**Column definitions:**
- **Day Due** — day of month from config `due_day` OR extracted from Monarch `due_date`
- **Amount** — from config or Monarch recurring
- **Method** — from config (auto_draft, auto_pay, manual, etc.)
- **Last Paid** — from Monarch `last_paid_date`
- **Status** — ✅ Current, ⚠️ Due Soon, ❌ Overdue, ❓ Unknown/Not Tracked, 🔌 Disconnected, 👤 Spouse

---

**SECTION 3: Personal Essential Bills**

Non-property bills with consequential service disruption (cell phone, auto insurance, child
support, etc.). Numbered sequentially. Same table format as properties.

---

After all sections, summarize:
- Total bills tracked vs expected
- Number of gaps (expected but not found)
- Number of untracked discoveries (in Monarch but not in config)
- Action items for the user

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

## Recurring List Hygiene

The Monarch recurring list should be curated so it cleanly reflects real obligations.
Every stream should fall into one of the three sections (credit accounts, properties,
personal). If a stream doesn't fit any section, work with the user to resolve it:

- **Is it a real bill?** → Add it to the appropriate config section
- **Is it a subscription, not a consequential bill?** → Mark inactive in Monarch
  via `update_recurring(stream_id, status="inactive")`
- **Is it stale/phantom?** → Investigate and mark inactive or remove
- **Is the category wrong?** → The user should recategorize in Monarch so it
  matches (or stops matching) the bill filter patterns
- **Is the merchant wrong/duplicated?** → See Multi-Stream Merchant Resolution

The goal is a clean recurring list where every item is accounted for. Do NOT
filter noise at the agent level — fix it at the source in Monarch. The bill_filters
exist to identify what matters from a clean list, not to compensate for a messy one.

After presenting the bill inventory, if there are recurring streams that don't fit
any section, list them separately and ask the user how to handle each one:

| Stream | Amount | Category | Suggestion |
|--------|--------|----------|------------|
| Gaylord Hotels | $35.63 | Adult Outings | Not a bill — mark inactive? |
| Urban Air | $46.62 | Family Activities | Not a bill — mark inactive? |

## Important Notes

- Update config incrementally as you discover info — don't wait until the end
- If a bill isn't in config but should be tracked, use register tools to add it
- If a recurring stream isn't in config, suggest adding it or adding a filter pattern
- Some credit cards may not be in Monarch (store cards, new cards) — check email
