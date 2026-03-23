# TODO — Bills Agent

Open work items not already captured in GitHub issues.
For issue-tracked work, see: https://github.com/krisrowe/bills-agent/issues

---

## Architecture

### A2: Category group enrichment for reliable skip classification
**Problem:** Income/transfer detection uses fnmatch glob patterns on user-customized category names (e.g., `*Net Pay*`, `*Transfer*`). Fragile, user-specific, breaks when categories are renamed.
**Fix:** Use Monarch's `group.type` field (`income`, `transfer`, `expense`) instead of name patterns. PostToolUse hooks already cache categories with `group.type`. The SDK just needs to use it instead of fnmatch.
**Design principle:** Prefer Monarch's native data model constructs over pattern matching on user-customized names.

**Analysis (confirmed 2026-03-20):** Queried all 158 categories in Monarch. Every category has a `group` with a `type` field that is one of: `income`, `transfer`, `expense`. This is a Monarch system-level classification — users can customize category names and move categories between groups, but the group types themselves are fixed by Monarch.

Verified against a live Monarch account: all income-type categories (12 total) have `group.type == "income"`, and all transfer-type categories (17 total) have `group.type == "transfer"`. No exceptions found.

**Conclusion:** `group.type == "income"` or `group.type == "transfer"` fully replaces all fnmatch skip patterns. The `skip_patterns` section in `config.yaml` can be removed entirely once this is implemented. Works for every Monarch user regardless of custom category naming.

**Open questions about category assignment on recurring streams:**
The recurring query returns category per occurrence, not per merchant. But we don't fully understand HOW Monarch assigns that category:

- **Unknown:** Whether recategorizing a transaction retroactively updates the category on its corresponding recurring stream occurrence.
- **Unknown:** How Monarch assigns category to FUTURE occurrences (no transaction yet). Is it the merchant's most recent transaction category, the most common, or the auto-categorization rule?
- **Unknown:** For split merchants (e.g., an insurer with separate auto and home policies paid from different accounts), whether each merchant's recurring occurrences automatically get the correct category based on the account-specific categorization rules.
- **Unknown:** What the "Refresh" button on the Recurring UI page does. It has a cooldown and may re-derive categories from transactions, or may do something else entirely.
- **Known:** Monarch has auto-categorization rules tied to merchants (`ruleCount` field on merchant query). These likely drive the category assignment but the exact mechanics are undocumented.
- **Known:** Each recurring occurrence CAN have a different category from another occurrence of the same stream.

**Risk:** If Monarch assigns an incorrect category to a recurring occurrence (e.g., a transfer stream gets categorized as an expense by a user rule), the group.type check would fail to skip it. Low risk — current fnmatch approach has the same vulnerability.

---

## Presentation / Skill

### P4: First-run inflation of unidentified section
**Problem:** On first run with no merchant IDs linked, property bill streams (mortgages, utilities) fall through to unidentified. Primary residence mortgage shows as both a declared-only property bill AND a detected-only unidentified stream. Count is inflated and misleading.
**Fix:** Consider — should streams that clearly belong to a property (by account association or category) be flagged differently? Or accept that first-run is noisy and it cleans up after linking? Property-level `funding_account` (D4) could help with tentative association.

---

## Data Model / Config

### D4: Property-level funding_account for stream-to-property assignment
**Problem:** Stream-to-property assignment requires knowing which bank account belongs to which property. Currently inferred from bill-level `funding_account` fields.
**Fix:** The `funding_account` field already exists on the Property model. Inventory function should use it to auto-assign unclaimed Monarch streams to properties by matching `account_id`. Bill-level `funding_account` overrides for bills paid from a different account.

### D5: Slot-based matching instead of name-based
**Problem:** Inherited bill matching by display name breaks on "Electric/Gas" vs "Electric + Gas".
**Fix:** Add optional `slot` field to bill entries. When present, match by slot. When absent, fall back to name matching. Long-term: all template bills have slots, user bills reference them.

### D7: Config management tools
**Problem:** No way to inspect or manage config outside of direct YAML editing.
**Fix:** Add SDK functions + MCP tools: export current resolved config, import from file, reset to defaults, show package-level templates and their bills.

---

## Exploration / Research

### R1: MCP elicitation support in Claude Code (introduced 2026-03-16)
Claude Code added MCP elicitation support. Investigate whether we can use it to prompt the user mid-workflow — e.g., "which section do you want to tackle next?" or "should I ignore all these subscriptions?" Could improve the section-by-section review flow by letting the tool itself ask the user questions rather than relying on the agent to mediate.
