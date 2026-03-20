# Contributing to Bills Agent

This document covers the design, architecture, and principles behind bills-agent. Read this before contributing code.

---

## What Bills Agent Does

Bills Agent is a Claude Code plugin that cross-references user-declared bill expectations against Monarch Money's live recurring transaction data. It catches overdue payments, missing bills, promo deadline risks, and disconnected accounts.

The user declares: "I own these properties, I have these credit accounts, I expect these bills." Monarch provides: "Here's what I see happening." The agent compares the two and flags discrepancies.

## Design Goals

**Expectations vs Actuals.** The config is not a transaction register — it's a declaration of what should exist. Monarch's `list_recurring` is the live source of what does exist. The value is in the gap between the two.

**Consequential Bills Only.** Track only bills with material consequences for non-payment: credit damage, service disconnection, foreclosure, insurance lapse. Not subscriptions, not medical bills, not incidental expenses.

**Clean Data Over Workarounds.** When the agent encounters stale or incorrect data in Monarch (e.g., a phantom recurring stream for a closed loan), the correct response is to help the user fix it in Monarch — not to add ignore-lists, blacklists, or exclusions to the config. If something passes the bill filter, it is a bill.

**Config Stores What Monarch Can't.** The config should only contain data Monarch doesn't provide: expected bills per property, payment methods, managed-by designations, promo financing deadlines, and bill filter patterns. Everything else comes from Monarch at query time.

## Architecture

### Where Things Live

```
BILLS-AGENT REPO (this repo — defines HOW to check bills)
  bills/sdk/common/           ← business logic, testable, reusable
    config.py                 ← Pydantic models, XDG paths, load/save
    accounts.py               ← credit account + promo SDK functions
    properties.py             ← property + bill SDK functions
    filters.py                ← bill filter pattern matching (fnmatch)
    budget.py                 ← budget scope SDK functions
  bills/mcp/server.py        ← thin MCP wrapper, calls SDK
  bills/cli.py               ← CLI commands (launch, register)
  claude/plugin/             ← Claude Code plugin
    .claude-plugin/plugin.json
    .mcp.json                 ← points to bills-mcp command
    skills/check/SKILL.md     ← cross-reference workflow
    skills/explain/SKILL.md   ← CC balance walkthrough

USER CONFIG (~/.config/bills/ — user's declared expectations)
  config.yaml                 ← credit accounts, properties, bills,
                                 funding accounts, bill filters, promos

MONARCH MONEY (live data at query time)
  list_recurring              ← detected recurring streams
  list_transactions           ← transaction history
  list_accounts               ← account balances and sync status
```

### Two MCP Servers, One Skill

The `/bills:check` skill orchestrates tools from two independent MCP servers:

- **bills-mcp** (bundled with plugin) — reads/writes the local config
- **monarch-access** (external, must be separately installed) — queries Monarch API

The plugin does not bundle monarch-access. It must be registered in the user's Claude Code session independently. The skill references tools from both servers and the agent resolves them at runtime.

### What the Config Tracks

| Section | Purpose | Monarch equivalent |
|---------|---------|-------------------|
| `credit_accounts` | Declared credit accounts with payment method, due day, promos | Monarch has accounts but not payment method or promo deadlines |
| `properties` | Properties with expected bills (mortgage, water, trash, etc.) | Monarch has no concept of property grouping |
| `funding_accounts` | Checking/savings accounts that pay bills | Monarch has accounts but no "pays for" relationship |
| `bill_filters` | Category patterns defining consequential bills | N/A — this is the filter on Monarch's data |
| `budget_scope` | Which bill categories count toward cash flow | N/A — planning concern |

### Bill Filters

`bill_filters.categories` contains glob patterns (processed via `fnmatch`, case-insensitive) that match against Monarch recurring stream category names. A stream matching any pattern is a "consequential bill."

The filter is intentionally inclusive. If a match is wrong, the fix belongs in Monarch (remove the stale recurring stream or recategorize it), not in the filter config.

### Promo Financing

Monarch has no concept of deferred interest deadlines. The config tracks promo plans with balance, expiration date, payment amount, and staleness (`updated` field). The skill calculates whether the payment schedule clears the balance before the deadline and flags insufficient payments.

Promo deadlines are the highest-priority items because missing one triggers retroactive interest on the full balance.

## Code Architecture

### SDK Layer First

All business logic lives in `bills/sdk/`. MCP server and CLI are thin wrappers.

```
bills/sdk/common/
  config.py       ← models + load/save
  accounts.py     ← credit account + promo operations
  properties.py   ← property + bill operations
  filters.py      ← bill filter operations + fnmatch
  budget.py       ← budget scope operations
  inventory.py    ← bill inventory: ID-based join logic + accountability
  ignored.py      ← ignored merchant management
  defaults.yaml   ← property type templates + skip patterns

bills/mcp/
  server.py       ← MCP tool definitions, calls SDK

bills/
  cli.py          ← CLI commands, calls SDK
```

If you're writing logic in server.py or cli.py, stop and move it to SDK.

### Config Models (Pydantic)

- `PromoFinancing` — a promo plan on a credit account
- `CreditAccount` — a credit account with payment method, promos, and Monarch ID links
- `PropertyBill` — a bill associated with a property, with Monarch merchant link
- `IgnoredMerchant` — a Monarch merchant explicitly classified as ignorable
- `Property` — a property with bills (type: residence, rental_longterm, rental_vacation, land, personal)
- `FundingAccount` — a checking/savings account
- `BillFilterConfig` — glob patterns for filtering Monarch categories
- `BudgetScopeConfig` — which categories count toward cash flow
- `BillsConfig` — root model containing all of the above

Config is stored as YAML at `~/.config/bills/config.yaml` following XDG conventions.

## Plugin Structure

```
claude/plugin/
├── .claude-plugin/
│   └── plugin.json          # name: "bills", version
├── .mcp.json                # mcpServers.manager → bills-mcp
├── skills/
│   ├── check/
│   │   └── SKILL.md         # 3-phase: load → reconcile → report
│   └── explain/
│       └── SKILL.md         # CC balance segment walkthrough
```

### Skill: check

Four phases:
1. **Load** — call `list_recurring` + `list_accounts` from monarch-access, load config from bills-mcp (parallel, read-only)
2. **Reconcile** — link config entries to Monarch entities by ID, classify unmatched streams, persist decisions to config (interactive, skipped if already linked)
3. **Report** — call `build_bill_inventory` with Monarch data, present alerts + sections + accountability (deterministic, no fuzzy matching)
4. **Triage & Fix** — walk user through fixing problems surfaced by the report: overdue items, stale streams, merchant splits, wrong categories, disconnected accounts (uses monarch-access tools)

### Skill: explain

Walks through a credit card's transaction history in segments (between payments/statement dates), showing large charges individually and small charges summarized, with running balance reconciliation.

## Development Loop

### Testing locally (no commit/push needed)

For skill changes (SKILL.md) — just restart Claude Code with the local plugin:
```bash
claude --plugin-dir ~/ws/bills-agent/claude/plugin
```

For SDK/MCP code changes (inventory.py, server.py, etc.) — also reinstall the package:
```bash
pipx install --force .
claude --plugin-dir ~/ws/bills-agent/claude/plugin
```

This loads the plugin directly from your working tree. No commit, no push, no marketplace update. Iterate until it works, then release.

### Releasing Changes

When ready to ship (skills, MCP tools, config models):

1. Make your code changes
2. Run tests: `python -m pytest tests/`
3. **Bump the version** in `claude/plugin/.claude-plugin/plugin.json` — Claude Code uses this to detect updates. If you don't bump it, users running `claude plugin update` won't see your changes.
4. Commit and push
5. Reinstall locally: `pipx install --force .`

### Versioning Strategy

- **Minor version** (0.5.0 → 0.6.0): new features, new tools, new config fields, skill rewrites
- **Patch version** (0.5.0 → 0.5.1): bug fixes, packaging fixes, doc updates, no new functionality

### Packaging Non-Python Files

Data files shipped with the package (e.g., `defaults.yaml`) must be declared in `pyproject.toml`:

```toml
[tool.setuptools.package-data]
"bills.sdk.common" = ["defaults.yaml"]
```

Without this, `pipx install` won't include them and the installed `bills-mcp` will crash at runtime with `FileNotFoundError`. Always verify after adding new data files:

```bash
pipx install --force .
ls $(python -c "import bills.sdk.common; print(bills.sdk.common.__path__[0])")/defaults.yaml
```

## Testing

- `python -m pytest tests/` runs all unit tests
- Tests are isolated via `XDG_CONFIG_HOME` fixture — no real config touched
- Sociable unit tests — no mocks, real config read/write to temp dirs
- Test names describe scenario + outcome, not implementation

## Data Privacy

This repo is PUBLIC. All personal data lives in `~/.config/bills/` at runtime, never in the repo. Use generic examples only in code, tests, and documentation.

## Design Principles

### Fix the Source, Not the Filter

When Monarch data is wrong (stale recurring streams, phantom entries), the correct response is to fix Monarch — not to add exclusions or workarounds in the config. The bill filter is intentionally inclusive: if something matches, it's treated as a real bill.

### Config Is Expectations, Not History

The config declares what should exist. It does not store transaction history, payment dates, or balances — those come from Monarch at query time. The only exception is promo financing, where Monarch has no equivalent data.

### Two Systems, One Truth

Neither config nor Monarch alone tells the full story. Config without Monarch can't tell you if a bill was paid. Monarch without config can't tell you if a bill is missing. The skill exists to bridge this gap.

### Properties Define Minimum Bill Sets

If you own a property, you expect certain bills (mortgage, water, electric, trash, insurance). If one stops showing up in Monarch, that's a signal — not something to ignore. Property declarations are the "minimum viable bill set" for each property.

### Prefer Monarch's Data Model Over Pattern Matching

When classifying recurring streams (income, transfer, expense), prefer Monarch's native
data model constructs (category groups, account types) over pattern matching on
user-customized category names. Patterns are fragile — they break when users rename
categories and aren't portable. Category `group.type` (income/transfer/expense) is a
Monarch system-level classification that works universally. See `docs/TODOS.md` A2.

### Persist Only What Monarch Can't Provide

Config should store information Monarch doesn't know: property types, mortgage status,
which property a bill belongs to, who manages it, payment method. It should NOT duplicate
data Monarch provides live: amounts, due dates, vendor names, payment status. These go
stale. The config is the human-knowledge layer; Monarch is the live-data layer.

### Stream-to-Property Assignment via Funding Accounts

Each property can have a dedicated bank account (funding_account). When a Monarch stream's
account matches a property's funding account, the stream belongs to that property. This is
deterministic and requires no fuzzy matching. For users with property-specific accounts,
this auto-assigns most streams without user input. For users with shared accounts, streams
fall through to manual classification.

### Bill Configuration: Current vs Future

**Current:** PropertyBill entries store vendor, amount, due_day, payment_method,
funding_account, managed_by, and monarch_merchant_id. Bills are declared explicitly or
created by the agent during reconciliation.

**Future direction:** May evolve to a thinner `merchant_slots` mapping — just
`{merchant_id: slot_name}` per property, plus optional overrides (managed_by,
payment_method). Everything else comes from Monarch live. This eliminates stale config
but requires the merchant-to-slot association to be persisted since Monarch categories
don't distinguish electric from water from trash within the same category group.

**Alternatives considered and rejected:**

- *Restructuring Monarch categories* to map to framework slots. Rejected: couples
  Monarch's tax-reporting category structure to this tool's needs. Not portable.

- *Fully automatic bill discovery* with zero config. Rejected: category groups distinguish
  income/transfer/expense but can't distinguish which utility is which within a property.
  Merchant-to-slot mapping requires human judgment at least once.

- *Auto-creating config entries on first check*. Rejected: makes one run special, creates
  entries that go stale. Better to derive fresh and only persist the merchant association.

## Future Enhancements

### CLI-Driven Project Install

A `bills install` (or `bills setup`) CLI command that bootstraps a Claude Code project for bill checking:

1. **Verify prerequisites** — check that `monarch-access` is installed and accessible (e.g., `which monarch-mcp` or test MCP connectivity). If missing, offer to install it locally as stdio given a Monarch token.
2. **Install/update the plugin** — run the Claude Code plugin install commands (`claude plugin marketplace add`, `claude plugin install`) or reinstall the latest version into the project at CWD.
3. **Configure safe tool permissions** — add read-only tools from both `bills-mcp` and `monarch-access` to the project's `.claude/settings.json` allow-list so Phase 1 data loading doesn't require per-tool approval. Tools to auto-allow:
   - `mcp__plugin_bills_manager__list_*`, `get_*`, `show_*`, `validate_*`
   - `mcp__monarch-access__list_*`, `get_*`
4. **Validate config** — run `validate_config` and report any issues with the user's `~/.config/bills/config.yaml`.

This reduces the friction of first-time setup and ensures consistent configuration across projects that use the bill checking workflow.
