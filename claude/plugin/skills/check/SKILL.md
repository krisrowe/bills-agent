---
name: check
description: Review bill payment status by cross-referencing your declared expectations (config) against Monarch's recurring list and transactions. Use when asked about bills, payments due, or to check on financial obligations.
---

# Check Bills Skill

Four-phase workflow: Load → Reconcile → Report → Triage & Fix. Matching is deterministic
by ID — config entries link to Monarch entities via `monarch_merchant_id` and `monarch_account_id`.

## Data Sources

This skill uses tools from **two MCP servers**:

**bills-mcp** (config + inventory):
- `build_bill_inventory` — primary report tool: cross-references config against Monarch data by ID
- `list_credit_accounts`, `list_properties`, `list_funding_accounts` — inspect config
- `list_promo_accounts` — credit accounts with active promo financing (high priority)
- `get_bill_filters` — category patterns defining consequential bills
- `update_credit_account`, `update_property_bill` — persist Monarch ID links during reconciliation
- `add_ignored_merchant`, `remove_ignored_merchant`, `list_ignored_merchants` — manage ignored merchants
- `register_property_bill`, `register_credit_account` — add newly discovered items
- `add_promo`, `update_promo`, `remove_promo` — manage promo financing plans
- `update_property` — update property metadata (type migration, address, etc.)

**monarch-access** (live data):
- `list_recurring` — recurring streams with payment status (is_past, transaction_id, due_date, last_paid_date)
- `list_accounts` — account balances, credential/sync status, account types
- `list_transactions` — transaction history for investigation and merchant splitting
- `update_recurring` — deactivate (`status="inactive"`) or remove (`status="removed"`) streams; also re-enable (`status="active"`) and update merchant recurring settings (amount, frequency, isActive)
- `update_transaction` — reassign transactions to new merchants (for splitting)

**Not yet available as MCP tools** (captured in monarch-access queries.py but not wired):
- `setMerchantLogo` — copy logos during merchant splits (manual workaround: user copies in Monarch UI)
- `merchants` search — search merchants by name

---

## Phase 0: Load (parallel, read-only)

Call in parallel — no user interaction needed:

**From monarch-access:**
- `list_recurring` — all active recurring streams
- `list_accounts` — all accounts with balance, credential status, and account type

**From bills-mcp:**
- `list_credit_accounts` — declared credit accounts (check for missing monarch IDs)
- `list_properties` — declared properties and bills (check for missing monarch IDs)
- `list_funding_accounts` — funding accounts with monarch_id links
- `list_promo_accounts` — accounts with active promo financing (check deadlines)
- `list_ignored_merchants` — explicitly ignored merchants
- `get_bill_filters` — category patterns for classifying unmatched streams

---

## Phase 1: Reconcile (interactive, only when needed)

**Skip this phase entirely** if all config entries have Monarch IDs linked and no
new unmatched streams appeared since last run. Quick check: every credit account has
`monarch_account_id` and `monarch_merchant_id`, every property bill has `monarch_merchant_id`.

### Step 1a: Credit accounts

**Link config → Monarch account (for balance/credential):**

For each config credit account without `monarch_account_id`:
- Filter Monarch `list_accounts` results by account type containing "credit"
- Search for last4 match in displayName (e.g., "CREDIT CARD (...9876)")
- Present match to user → confirm → `update_credit_account(last4, monarch_account_id=...)`

**Link config → Monarch payment stream (for payment tracking):**

For each config credit account without `monarch_merchant_id`:
- Search recurring streams for payment merchants — look for:
  - Category containing "Credit Card" or the issuer name
  - Amount plausible for a credit card payment
  - Account matching the funding_account
- Present match to user → confirm → `update_credit_account(last4, monarch_merchant_id=...)`

**Discover Monarch credit accounts not in config:**

For each Monarch account with credit type not linked to any config entry:
- "Monarch has CREDIT CARD (...4855) — track it?"
- Yes → `register_credit_account(name, issuer, last4, monarch_account_id=..., ...)` then link merchant
- No → skip (don't add to ignored_merchants — it's an account, not a stream)

### Step 1b: Property bills

For each config property bill without `monarch_merchant_id`:
- Search recurring streams for likely matches by:
  - Merchant name similar to vendor
  - Category matching the bill type (Mortgage, Utilities, Internet, etc.)
  - Amount close to expected
  - Account matching funding_account
- Present top candidate: "Stream 'LoanCo' ($2,100/mo, Mortgage) — link to Home → Mortgage?"
- Confirm → `update_property_bill(property, bill, monarch_merchant_id=...)`
- No match found → leave unlinked, will show as gap in report

### Step 1c: Unmatched streams

For each Monarch recurring stream not linked to any config entry, not in `ignored_merchants`,
and not caught by skip patterns (transfer/income categories):

Present to user with: merchant name, amount, frequency, category, account

Three options:
- **Track it as a property bill** → `register_property_bill(property_name, bill_name, vendor,
  monarch_merchant_id=<stream's merchant_id>, ...)` — pre-links the merchant
- **Track it as a credit account** → `register_credit_account(...)` then link
- **Ignore it** → `add_ignored_merchant(merchant_id, name, reason)` where reason is one of:
  `subscription_inconsequential`, `income`, `transfer`, `other`
- **Fix in Monarch** → help recategorize (so skip patterns catch it), deactivate, or split

### Step 1d: Property type migration

For config properties with `type: rental` (old v1 format):
- Ask user: "Is [property] a long-term rental or vacation rental?"
- `update_property(name, type="rental_longterm")` or `update_property(name, type="rental_vacation")`
- This changes the framework template (expected bill slots) for that property

---

## Phase 2: Report (deterministic)

Call `build_bill_inventory` from bills-mcp, passing the Monarch data from Phase 0.
All matching is by ID — no fuzzy logic.

### Payment status determination

The inventory function determines status from Monarch stream data:

| Condition | Status |
|-----------|--------|
| `is_past=true` + `transaction_id` present | ✅ **paid** |
| `is_past=true` + no `transaction_id` | ❌ **overdue** |
| `is_past=false` + `due_date` within 7 days | ⚠️ **due_soon** |
| Config has `monarch_merchant_id` but no stream found | ❓ **unknown** (merchant may be deactivated) |
| Config has no `monarch_merchant_id` | ❓ **gap** (needs reconciliation) |
| Account `credential.updateRequired=true` | 🔌 **disconnected** |

### Present results in order:

**1. ALERTS** — immediate attention needed:
- ❌ Overdue payments (past due, no payment found)
- ⚠️ Promo deadlines — calculate for each promo:
  - Months remaining = days until `expires` / 30
  - Required monthly = `balance` / months remaining
  - Compare to `payment_amount` — flag if insufficient
  - <90 days = WARNING, <30 days = CRITICAL
  - `updated` field >30 days stale → flag for balance refresh
- 🔌 Disconnected accounts (credential needs refresh)

**2. Credit Accounts**

| # | Account | Last4 | Issuer | Day Due | Method | Status |
|---|---------|-------|--------|---------|--------|--------|

- **Status** from Monarch via `monarch_merchant_id` stream lookup
- **Balance** from Monarch via `monarch_account_id` account lookup
- Flag promo accounts beneath the table with: balance, expires, required monthly, payment amount

**3. Properties**

One sub-section per property. Framework-expected bills shown with static slot numbers.
Extra config bills (HOA, HELOC, etc.) get ad-hoc numbers. Gap items shown with ❓.

| # | Bill | Vendor | Day Due | Amount | Method | Last Paid | Status |
|---|------|--------|---------|--------|--------|-----------|--------|

Status icons: ✅ Paid, ⚠️ Due Soon, ❌ Overdue, ❓ Gap/Unknown, 🔌 Disconnected, 👤 Spouse

**For spouse-managed bills** (`managed_by` set in config):
- Only flag if actual problem detected (overdue, disconnected)
- Don't flag for missing config or collect detailed transaction history
- Show with 👤 icon — indicate it's monitored but not actively tracked

**4. Personal**

Non-property tracked bills from two sources:
- Bills on `personal`-type properties (explicit config with vendor, due_day, etc.)
- Streams matching `bill_filters` but with no config entry (discovered, Monarch evidence only)
Same table format as properties.

**5. Ignored** (compact)

Summary by reason: "25 auto-ignored (transfers, income), 10 explicitly ignored (subscriptions)"
Don't list individual items unless user asks.

**6. Unclassified** (should be empty after Phase 1)

| Stream | Amount | Category | Account |
|--------|--------|----------|---------|

If items appear here, Phase 1 reconciliation is incomplete. Offer to classify them now.

**7. Accountability**

"67/67 Monarch streams accounted for. 28/28 config expectations accounted for."

Show the grouped breakdown:
```
Monarch streams: 67 total
  17 matched to property bills
   5 matched to credit accounts
   3 matched by bill filter
  25 ignored by pattern
  10 ignored by merchant list
   7 unclassified
```

---

## Phase 3: Triage & Fix (interactive, post-report)

After presenting the report, walk the user through fixing problems it surfaced.
Use monarch-access tools to fix Monarch data directly. Use bills-mcp tools to
update config links afterward.

### Overdue / Gap items

For each ❌ Overdue or ❓ Gap/Unknown item:
- Search `list_transactions` for recent payments to that vendor/merchant
- Check if the account is disconnected (`credential.updateRequired`)
- Check if the merchant name changed (search for similar amounts around the time payments stopped)
- Check multiple merchant name variations (abbreviations, "Memorial" variants, etc.)
- Present findings to user — determine if it's a real missed payment or a data issue

### Missing streams (config linked but merchant gone from list_recurring)

When a bill has `monarch_merchant_id` but no matching stream appears in Monarch:

The most common cause is the merchant's recurring was turned off or marked as not recurring
in Monarch (by the user or automatically). Other causes: merchant renamed, consolidated,
or the obligation genuinely ended.

Investigation:
- Search `list_transactions` for recent payments from that merchant — if payments are
  still happening, the recurring just needs to be re-enabled
- Search recurring streams for new merchants with similar amounts/categories that appeared
  around the time the old one disappeared

Resolution:
- Recurring was turned off → re-enable via `update_recurring` with `status="active"`,
  or use `update_recurring` to set `isRecurring: true` with correct amount/frequency
- Merchant was renamed/replaced → update config link to the new merchant_id
  via `update_property_bill(..., monarch_merchant_id=<new_id>)` or `update_credit_account`
- Bill was paid off (loan closed, promo cleared) → remove the bill from config
- Merchant incorrectly removed → user recreates by categorizing a recent transaction,
  then set up recurring on the new merchant via `update_recurring`

### Stale streams (last_paid_date > 4 months ago or null)

Don't assume dead. Could be:
- Closed/paid off → `update_recurring(stream_id, status="inactive")`
- Merchant renamed → find new merchant, link config to it, deactivate old
- Loan transferred to new servicer → same approach (search for new merchant with similar amount)
- Credential disconnected → flag for user to re-authenticate in Monarch
- Payment comes from an account not linked to Monarch

Search `list_transactions` for similar amounts in the relevant accounts. Present findings
before taking action — always confirm with user before deactivating.

### Duplicate / split merchants

When one merchant handles multiple obligations (e.g., insurer with auto + home + rental policies
paid from different accounts with different amounts):

**Detection:** A recurring stream's amount doesn't match actual transaction amounts, OR
transactions from the same merchant post to multiple accounts with different amounts.

**Resolution workflow:**
1. Search `list_transactions` for the merchant, group by account + amount pattern
2. `update_transaction(id, merchant_name="New Descriptive Name")` for each group — Monarch auto-creates the merchant
3. `update_recurring` on the new merchant to set correct amount, frequency, and baseDate
4. Copy logo: `setMerchantLogo` with original's cloudinary public ID (if available as MCP tool; otherwise user copies in Monarch UI)
5. `update_recurring(stream_id, status="inactive")` on the original merchant's stream
6. Update config: `update_property_bill(..., monarch_merchant_id=<new_merchant_id>)`

### Wrong categories

If a stream has the wrong category (causing it to be misclassified by bill_filters or skip_patterns):
- User recategorizes in Monarch UI
- Or agent recategorizes via `update_transaction` on recent transactions (category change propagates)
- Next check run will classify correctly based on the new category

### Promo balance refresh

For promo accounts with `updated` field >30 days stale:
- Look up current balance from Monarch account data or recent statement
- `update_promo(account_last4, promo_index, balance=<new_balance>, updated=<today>)`
- Recalculate: does payment_amount * months_remaining >= balance?
- If not, alert user that the payment plan is insufficient

### Disconnected accounts

For 🔌 Disconnected items:
- Alert user that Monarch credentials need refresh for the specific institution
- Check if other accounts from the same institution are also disconnected
- User logs into Monarch to re-authenticate
- Next check run will show live data once credentials are refreshed

Detection heuristics beyond `credential.updateRequired`:
- No transactions for an account in 30+ days
- Balance unchanged for multiple weeks on an active account
- These suggest a silent disconnection even if credential flag isn't set

---

## Email Search (fallback)

When Monarch data is insufficient for a bill (no recurring stream, no recent transactions),
search **both configured email profiles** for:
- Statement notifications from the vendor
- Payment confirmations
- Due date reminders
- Account alerts or past-due notices

This is particularly useful for:
- Store cards / vendor financing not connected to Monarch
- Bills paid outside Monarch-linked accounts
- New accounts not yet set up in Monarch

---

## Payment Method Values

- `auto_draft` — Creditor pulls from bank account (mortgage, some utilities)
- `auto_pay` — Bank pushes scheduled payment (bill pay)
- `auto_pay_full` — Autopay for full statement balance (credit cards)
- `auto_pay_min` — Autopay for minimum payment only (credit cards)
- `manual` — Requires manual payment each cycle

---

## Important Notes

- Every item from every source appears exactly once in the output — nothing silently dropped
- Config = expectations + Monarch ID links. Monarch = live state.
- Fix data in Monarch, don't add workarounds in config
- Property type `rental` in old configs needs migration to `rental_longterm` or `rental_vacation` — Phase 1 handles this
- After a few runs, reconciliation becomes a no-op and the skill goes straight to the report
- Update config incrementally as you discover info — don't wait until the end
- Some credit cards may not be in Monarch (store cards, new cards) — check email
