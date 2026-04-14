# Monarch Default Categories — Reference

Source: https://help.monarch.com/hc/en-us/articles/360048883851-Default-Categories
(Last updated by Monarch: January 3, 2026. Captured: 2026-04-14.)

This document exists as a stable reference for the `/bills:credit-cards` skill
and other bills-agent workflows that reason about Monarch's category taxonomy.
Use it to understand what categories any Monarch user starts with, and how
the skill should behave against default-shaped configurations.

## Group type is a platform-level field

Every Monarch category belongs to a group. Groups have a `type` field with one
of three values:

- `income`
- `expense`
- `transfer`

This is **not user-defined** — it is part of Monarch's data model and
exposed via `list_categories` as `category.group.type`. Use it as the
universal anchor when writing portable logic.

## Default categories

### Income (group.type: `income`)

- Paychecks
- Interest
- Business Income
- Other Income

### Expenses (group.type: `expense`)

**Gifts & Donations**
- Charity
- Gifts

**Auto & Transport**
- Auto Payment
- Public Transit
- Gas
- Auto Maintenance
- Parking & Tolls
- Taxi & Ride Shares

**Housing**
- Mortgage
- Rent
- Home Improvement

**Bills & Utilities**
- Garbage
- Water
- Gas & Electric
- Internet & Cable
- Phone

**Food & Dining**
- Groceries
- Restaurants & Bars
- Coffee Shops

**Travel & Lifestyle**
- Travel & Vacation
- Entertainment & Recreation
- Personal
- Pets
- Fun Money

**Shopping**
- Shopping
- Clothing
- Furniture & Housewares
- Electronics

**Children**
- Child Care
- Child Activities

**Education**
- Student Loans
- Education

**Health & Wellness**
- Medical
- Dentist
- Fitness

**Financial**
- Loan Repayment
- Financial & Legal Services
- Financial Fees
- Cash & ATM
- Insurance
- Taxes

**Other**
- Uncategorized (cannot be disabled)
- Check
- Miscellaneous

**Business**
- Advertising & Promotion
- Business Utilities & Communication
- Employee Wages & Contract Labor
- Business Travel & Meals
- Business Auto Expenses
- Business Insurance
- Office Supplies & Expenses
- Office Rent
- Postage & Shipping

### Transfers (group.type: `transfer`)

- Transfer
- Credit Card Payment
- Balance Adjustments

### Investment transactions (beta) — appear after first investment sync

- Buy (transfer subgroup)
- Sell (transfer subgroup)
- Dividends & Capital Gains (income subgroup)

## Implications for bills-agent

### 1. Defaults double-count debt service as expense

Monarch's defaults put most debt-servicing categories in **expense** groups,
not transfer:

- `Mortgage` → Housing (expense)
- `Auto Payment` → Auto & Transport (expense)
- `Loan Repayment` → Financial (expense)
- `Student Loans` → Education (expense)

Only `Credit Card Payment` lives in Transfers by default. A user who accepts
defaults and lets Monarch auto-categorize their mortgage or auto loan payment
will see those payments appear as expenses in their spending reports, inflating
apparent expense totals by the full debt-service amount.

The `/bills:credit-cards` skill should detect and surface this as a hygiene
finding when it encounters it, and propose moving debt-service categories
into a transfer-type group (or creating custom transfer categories for them).

### 2. The skill cannot rely on category name strings

Category names can be renamed, disabled, or supplemented by the user. The
skill must filter by `group.type`, not by string matching on
`"Credit Card Payment"` or `"Loan Repayment"`.

### 3. Recommended skill behavior

- **Discover** categories every run via `list_categories`
- **Filter funding-side payment scans** to `group.type == "transfer"` by default
- **Flag** any transaction where the card-side is a CC payment (positive amount
  on a credit account) but the funding-side counterpart lives in an expense-type
  category — this is the double-counting anti-pattern
- **Accept user overrides** in bills-agent config for cases where the user has
  custom payment-shaped expense categories intentionally (e.g., tracking
  interest payments separately from principal)

### 4. Encouraging hygiene

When the skill finds debt-service payments in expense-type categories, it
should:

1. Note the finding (don't silently rewrite)
2. Explain the impact (double-counting in spending reports)
3. Offer concrete fixes:
   - Recategorize the specific transaction(s)
   - Suggest creating a custom transfer-type category if the user wants
     finer granularity than the single `Transfer` default
   - Suggest a Monarch rule to auto-categorize future occurrences

This makes the skill educational about Monarch hygiene, not just a
verification tool.
