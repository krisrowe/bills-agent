# Credit Card Verification

`/bills:check` cross-references your declared credit accounts against Monarch's
recurring streams. This works when streams are correctly linked, but Monarch's
autopay detection has known limitations with credit cards. `/bills:credit-cards`
bypasses stream matching entirely — it searches actual transaction history on
each card account.

## When to use which

**Use `/bills:check`** when your credit card configuration is mature:
- Each card has a `monarch_account_id` linked
- Recurring streams are matched to the right accounts
- Last paid dates in Monarch look accurate
- You want a fast pass across all bill types (properties + cards + promos)

**Use `/bills:credit-cards`** when:
- You're still building out your credit account config
- `/bills:check` shows something suspicious (overdue but you know you paid)
- You want to validate `/bills:check` results against real transactions
- Monarch's stream data is unreliable for cards (see problems below)

Both skills can be used in the same session. Run `/bills:check` first for the
full picture, then `/bills:credit-cards` to double-check the credit card section.

## Common problems with stream-based credit card detection

### Generic autopay merchant names

Your bank sends autopay payments to credit cards, but the merchant name is
something like "AUTOMATIC PAYMENT" or "ONLINE PAYMENT" — not the card issuer's
name. Monarch creates a recurring stream, but you can't tell which card it
applies to. `/bills:check` can't link the stream to the right account.

**Fix:** Split the merchant in Monarch so each card gets its own stream with a
recognizable name.

**Workaround:** `/bills:credit-cards` queries each card's account directly for
incoming payment transactions, so it doesn't need the stream at all.

### Last paid dates lagging or missing

Monarch shows a recurring stream's last paid date based on when it last detected
a matching transaction. If the merchant name changed slightly, or the payment
amount varies month to month, Monarch may stop updating the stream. The bill
looks overdue, but the payment actually went through.

**Fix:** Recategorize or merge the transactions in Monarch so the stream
recognizes them again.

**Workaround:** `/bills:credit-cards` checks actual transaction history on the
card account — it sees the payment credited regardless of stream status.

### Streams matched to the wrong account

A recurring stream gets associated with the funding account (checking account
where the payment originates) rather than the credit card account (where the
payment lands). The inventory engine links the stream to the wrong side of the
transaction.

**Fix:** Update the merchant link in bills config (`update_credit_account` or
`update_property_bill`) to point at the correct Monarch merchant.

**Workaround:** `/bills:credit-cards` queries each card's own transaction
history and cross-references funding accounts separately, so it gets the
direction right.

### Disconnected credentials

A bank login expires and Monarch stops syncing. The recurring stream goes stale,
the balance is outdated, and `/bills:check` can't verify payment status for
accounts at that institution.

**Fix:** Re-authenticate in Monarch.

**Workaround:** `/bills:credit-cards` falls back to searching the funding
side — it looks for outgoing payments from your checking accounts that match
the card issuer name. This catches payments even when the card's own account
data is stale.

### Multiple cards at the same issuer

You have two cards from the same bank. Monarch may merge their payment streams
or attribute payments from one card to the other.

**Fix:** Split the merchant in Monarch so each card gets a distinct recurring
stream.

**Workaround:** `/bills:credit-cards` queries each card independently by
Monarch account ID, so it never confuses which payment goes where.
