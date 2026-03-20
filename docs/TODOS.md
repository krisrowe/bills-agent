# TODO — Bills Agent

Captured from session 2026-03-17. Prioritized by impact.

---

## Architecture

### A1: bills-mcp imports monarch-access SDK directly
**Problem:** Agent is a dumb middleman carrying 40KB of Monarch data between two MCP servers. Causes "Large MCP response" warnings and context bloat.
**Fix:** `build_bill_inventory` tool takes zero arguments, internally imports monarch SDK and calls `list_recurring`/`list_accounts` directly. Same token file (`~/.config/monarch/token`), no duplicate credentials. Add `monarch-access` as a pip dependency.
**Impact:** Eliminates context pollution, simplifies agent workflow to one zero-arg tool call.

### A2: Category group enrichment for reliable skip classification
**Problem:** Income/transfer detection uses fnmatch glob patterns (Python's `fnmatch` function) on user-customized category names (e.g., `*Net Pay*`, `*Transfer*`). Fragile, user-specific, breaks when categories are renamed.
**Fix:** When fetching recurring streams, also fetch `list_categories` (one extra API call), build category_id → category group type mapping, enrich each stream with the group type. Use `group.type` for skip classification instead of name patterns.
**Where:** monarch-access `list_recurring` could do this internally, or bills-agent does the join if using A1.
**Design principle:** Prefer Monarch's native data model constructs over pattern matching on user-customized names.

**Analysis (confirmed 2026-03-20):** Queried all 158 categories in Monarch. Every category has a `group` with a `type` field that is one of: `income`, `transfer`, `expense`. This is a Monarch system-level classification — users can customize category names and move categories between groups, but the group types themselves are fixed by Monarch.

Verified against a live Monarch account: all income-type categories (12 total) have `group.type == "income"`, and all transfer-type categories (17 total) have `group.type == "transfer"`. No exceptions found.

**Conclusion:** `group.type == "income"` or `group.type == "transfer"` fully replaces all fnmatch skip patterns. The `skip_patterns` section in `defaults.yaml` can be removed entirely once this is implemented. Works for every Monarch user regardless of custom category naming.

**Open questions about category assignment on recurring streams:**
The recurring query returns category per occurrence, not per merchant. But we don't fully understand HOW Monarch assigns that category:

- **Unknown:** Whether recategorizing a transaction retroactively updates the category on its corresponding recurring stream occurrence.
- **Unknown:** How Monarch assigns category to FUTURE occurrences (no transaction yet). Is it the merchant's most recent transaction category, the most common, or the auto-categorization rule?
- **Unknown:** For split merchants (e.g., an insurer with separate auto and home policies paid from different accounts), whether each merchant's recurring occurrences automatically get the correct category based on the account-specific categorization rules.
- **Unknown:** What the "Refresh" button on the Recurring UI page does. It has a cooldown and may re-derive categories from transactions, or may do something else entirely.
- **Known:** Monarch has auto-categorization rules tied to merchants (`ruleCount` field on merchant query). These likely drive the category assignment but the exact mechanics are undocumented.
- **Known:** Each recurring occurrence CAN have a different category from another occurrence of the same stream.

**Risk for A2:** If Monarch assigns an incorrect category to a recurring occurrence (e.g., a transfer stream gets categorized as an expense by a user rule), the group.type check would fail to skip it. This is low risk but worth monitoring. The current fnmatch approach has the same vulnerability — a miscategorized stream would also bypass name-based patterns.

### A3: Minimize list_accounts response size
**Problem:** `list_accounts` returns ~600 bytes/account with fields bills-agent doesn't need (`includeInNetWorth`, `dataProvider`, `isManual`, `createdAt`, `updatedAt`, `syncDisabled`, `deactivatedAt`, `isHidden`, `isAsset`).
**Fix:** Add `fieldset` parameter to monarch-access `list_accounts` — `standard` (id, displayName, mask, type, subtype, currentBalance, credential.updateRequired, institution.name) vs `full` (everything). Default to `standard`.
**Where:** monarch-access repo.

---

## Presentation / Skill

### P1: Section summary table in initial output
**Problem:** User has no overview of what sections exist and what state they're in before diving into details. Creates anxiety about what's coming.
**Fix:** After `build_bill_inventory` manifest, show a summary table with per-section declared/detected/matched counts plus alert flags. Requires adding per-section breakdowns to the manifest response.

### P2: Ignored section needs transparency
**Problem:** "3 ignored" with no context creates suspicion. User doesn't know why, what, or who decided.
**Fix:** Ignored summary should show merchant names, amounts, and the specific reason (auto-skipped by category group vs manually ignored by user). For small counts (<10), show inline rather than requiring a section fetch.

### P3: Unclassified section needs a preview
**Problem:** "32 unclassified" gives no sense of what's in there.
**Fix:** Include top 5-10 merchant names in the manifest summary so user knows the flavor before fetching the full section.

### P4: First-run inflation of "personal" section
**Problem:** On first run with no merchant IDs linked, property bill streams (mortgages, utilities) fall through to bill_filter matching and appear as "personal" items. Primary residence mortgage shows as both a declared-only property bill AND a detected-only personal bill. Count is inflated and misleading.
**Fix:** Consider — should bill_filter matches that clearly belong to a property (by account association or category) be flagged differently? Or accept that first-run is noisy and it cleans up after linking?

---

## Data Model / Config

### D1: Design principle in CONTRIBUTING.md
**Problem:** No documented principle about preferring Monarch's native data constructs over pattern matching.
**Fix:** Add to CONTRIBUTING.md design principles: "Prefer Monarch's data model constructs (category groups, account types) over pattern matching on user-customized category names. Patterns are a last resort for things Monarch's model doesn't classify."

### D2: Update design doc (temp/) to reflect current state
**Problem:** `temp/design-complete-accountability.md` is out of date — doesn't reflect cached inventory, pre-grouped sections, declared/detected/matched terminology, or the phase reordering (report before reconcile).
**Fix:** Rewrite or retire. The code + SKILL.md + CONTRIBUTING.md are the living docs now.

---

## monarch-access Changes (separate repo)

### M1: Category group enrichment on list_recurring
See A2 above. Add category_group to each stream in `list_recurring` output.

### M2: Fieldset parameter on list_accounts
See A3 above. Add `fieldset=standard|full` parameter.

### M3: Minimize list_recurring output
Same idea as M2 — `list_recurring` includes `category_id`, `is_approximate`, and other fields bills-agent doesn't use. Consider a `fieldset` parameter here too.

---

## Exploration / Research

### R1: MCP elicitation support in Claude Code (introduced 2026-03-16)
Claude Code added MCP elicitation support. Investigate whether we can use it to prompt the user mid-workflow — e.g., "which section do you want to tackle next?" or "should I ignore all these subscriptions?" without the agent having to guess or dump everything at once. Could improve the section-by-section review flow by letting the tool itself ask the user questions rather than relying on the agent to mediate.
