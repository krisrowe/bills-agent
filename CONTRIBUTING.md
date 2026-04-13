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

**Data provider decoupling.** The SDK's inventory engine accepts streams, accounts,
and categories as plain data — it has no direct dependency on the Monarch API. The
Monarch coupling lives in the skills (which name monarch-access tools) and the hooks
(which parse Monarch response shapes). This architecture is ready for a provider
pattern where the data source could be another financial platform, a local CSV/OFX
ledger, or any MCP server that produces the same data shapes.

**Maintain this boundary.** Never import monarch-access or call the Monarch API from
SDK code. The SDK must remain data-source-agnostic — it receives data, it doesn't
fetch it. Monarch-specific logic belongs only in skills and hooks.

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
  config.py       ← Pydantic models + load/save
  config.yaml     ← package-level config: abstract templates + skip patterns
  accounts.py     ← credit account + promo operations
  properties.py   ← property + bill operations + inheritance resolution
  filters.py      ← bill filter operations + fnmatch
  budget.py       ← budget scope operations
  inventory.py    ← bill inventory: ID-based join logic + accountability
  ignored.py      ← ignored merchant management

bills/mcp/
  server.py       ← MCP tool definitions, calls SDK

bills/
  cli.py          ← CLI commands, calls SDK
```

If you're writing logic in server.py or cli.py, stop and move it to SDK.

### Config Models (Pydantic)

- `Property` — a property (concrete or abstract template) with bills, inheritance, and funding account
- `PropertyBill` — a bill on a property, with optional vendor, merchant link, managed_by, and remove flag
- `CreditAccount` — a credit account with payment method, promos, and Monarch ID links
- `PromoFinancing` — a promo plan on a credit account
- `FundingAccount` — a checking/savings account
- `IgnoredMerchant` — a Monarch merchant explicitly classified as ignorable
- `BillFilterConfig` — glob patterns for filtering Monarch categories
- `BudgetScopeConfig` — which categories count toward cash flow
- `BillsConfig` — root model containing all of the above

### Two-Layer Config

**Package config** (`bills/sdk/common/config.yaml`) ships with the code and defines abstract
property templates (residence, rental_vacation, rental_longterm, real_estate, personal) plus
skip patterns. This is the base layer.

**User config** (`~/.config/bills/config.yaml`) declares concrete properties that inherit from
templates, credit accounts, funding accounts, and ignored merchants. This is the override layer.

Properties merge by name. A concrete property inherits all bills from its template and can:
- Override bill fields (vendor, merchant_id, managed_by) by declaring a bill with the same name
- Exclude inherited bills with `remove: true`
- Add extra bills not in the template (HOA, HELOC, etc.)

### Property Inheritance

```yaml
# Package config (abstract templates)
properties:
  - name: real_estate
    abstract: true
    bills:
      - name: Mortgage
      - name: Property Tax

  - name: rental_vacation
    abstract: true
    inherit: real_estate
    bills:
      - name: Electric
      - name: Water
      - name: Trash
      - name: Internet
      - name: Insurance
      - name: Management

# User config (concrete properties)
properties:
  - name: Lake House
    inherit: rental_vacation
    funding_account: "1234"
    bills:
      - name: Management
        remove: true
      - name: Mortgage
        vendor: Mortgage Co
```

Lake House inherits Mortgage + Property Tax from real_estate (via rental_vacation),
plus Electric, Water, Trash, Internet, Insurance, Management from rental_vacation.
Then removes Management and adds a vendor to Mortgage. Result: 7 bills.

Abstract properties are skipped by the inventory — they're templates only. Concrete
properties (abstract=false, the default) are processed.

Removing an inherited bill via the `remove_property_bill` tool raises `InheritedBillError` —
use `remove: true` instead. Updating an inherited bill creates a local override entry.

## Plugin Structure

```
claude/plugin/
├── .claude-plugin/
│   └── plugin.json          # name: "bills", version
├── .mcp.json                # mcpServers.manager → bills-mcp
├── hooks/
│   ├── hooks.json           # PostToolUse hook definitions
│   └── cache_monarch.py     # intercepts Monarch responses, caches to disk
├── skills/                    # Agent Skills standard (agentskills.io)
│   ├── check/
│   │   └── SKILL.md         # 4-phase: load → reconcile → report → triage
│   └── explain/
│       └── SKILL.md         # CC balance segment walkthrough
```

### Hooks

The plugin registers PostToolUse hooks that fire after `list_recurring`,
`list_accounts`, and `list_categories` calls to any MCP server (matched via
regex `mcp__.*__list_recurring`, etc.).

Each hook runs `cache_monarch.py <resource_type>`, which:

1. Reads the MCP tool response from stdin (hook input JSON)
2. Extracts only the fields `build_bill_inventory` needs (defined in `RECURRING_FIELDS`, `ACCOUNT_FIELDS`)
3. Writes canonical JSON to `~/.local/share/bills/monarch_<type>.json`
4. Replaces the full MCP response with a short summary (count + cache path) via `updatedMCPToolOutput`

This keeps Monarch responses (often 50-100KB) out of the conversation context.
The inventory engine reads from these cache files automatically.

**Without hooks:** The full Monarch responses remain in context. The inventory
engine still works — it accepts data directly or reads from the default cache
paths. Hooks are a Claude Code optimization, not a requirement.

### Skill: check

Four phases:
1. **Load** — call `list_recurring` + `list_accounts` + `list_categories` from monarch-access (hooks cache to disk), then `build_bill_inventory` with cache paths
2. **Reconcile** — link config entries to Monarch entities by ID, classify unmatched streams, persist decisions to config (interactive, skipped if already linked)
3. **Report** — present alerts + sections + accountability from inventory (deterministic, no fuzzy matching)
4. **Triage & Fix** — walk user through fixing problems surfaced by the report: overdue items, stale streams, merchant splits, wrong categories, disconnected accounts (uses monarch-access tools)

### Skill: explain

Walks through a credit card's transaction history in segments (between payments/statement dates), showing large charges individually and small charges summarized, with running balance reconciliation.

## CLI

The `bills` CLI (`bills/cli.py`) provides launch helpers, MCP server registration,
and standalone reports. It is a thin wrapper — no business logic.

### Commands

| Command | Description |
|---------|-------------|
| `bills claude` | Launch Claude Code with the bills plugin attached (`--plugin-dir`) |
| `bills gemini` | Launch Gemini CLI with the bills extension |
| `bills register claude [--scope user\|project]` | Register `bills-mcp` in Claude Code settings |
| `bills register gemini` | Link bills extension with Gemini CLI |
| `bills unregister claude [--scope user\|project]` | Remove `bills-mcp` from Claude Code settings |
| `bills-report summary [--format text\|json]` | Config summary (account/property/promo counts) |
| `bills-report overdue` | Overdue detection (stub — needs Monarch integration) |
| `bills-report due-soon` | Due-soon detection (stub — needs date calculation) |

### Entry points (pyproject.toml)

- `bills` → `bills.cli:main`
- `bills-mcp` → `bills.mcp.server:run_server`
- `bills-report` → `bills.cli:report`

## Development Loop

### Testing locally (no commit/push needed)

For skill changes (SKILL.md) — just restart Claude Code with the local plugin:
```bash
claude --plugin-dir path/to/bills-agent/claude/plugin
```

For SDK/MCP code changes (inventory.py, server.py, etc.) — also reinstall the package:
```bash
pipx install --force .
claude --plugin-dir path/to/bills-agent/claude/plugin
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

Data files shipped with the package (e.g., `config.yaml`) must be declared in `pyproject.toml`:

```toml
[tool.setuptools.package-data]
"bills.sdk.common" = ["config.yaml"]
```

Without this, `pipx install` won't include them and the installed `bills-mcp` will crash
at runtime with `FileNotFoundError`.


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

### README vs CONTRIBUTING

README is for anyone using the tool — installation, configuration concepts, tool
interfaces, and how the system works from a user perspective. CONTRIBUTING is for
anyone modifying the code — architecture, design decisions, tradeoffs, and
implementation details. If a user needs to know it to use the tool, it goes in README.
If a developer needs to know it to change the code, it goes in CONTRIBUTING.

### Config Is Managed Through Tools, Not Direct Editing

Users should never need to edit YAML directly. MCP tools, CLI commands, and the skill
workflow must provide full control over configuration — declaring properties, inheriting
templates, excluding bills, linking merchants, managing ignored streams. All user-facing
documentation should describe tool interfaces, not raw YAML. The only exception is
import/export/diff operations where the YAML representation is the point.

### Config Is Expectations, Not History

The config declares what should exist. It does not store transaction history, payment dates, or balances — those come from Monarch at query time. The only exception is promo financing, where Monarch has no equivalent data.

### Two Systems, One Truth

Neither config nor Monarch alone tells the full story. Config without Monarch can't tell you if a bill was paid. Monarch without config can't tell you if a bill is missing. The skill exists to bridge this gap.

### Properties Inherit Expected Bills

Abstract templates define the minimum bill set per property category. Concrete properties
inherit from templates and override as needed. If an expected bill stops showing up in
Monarch, that's a signal — not something to ignore.

### Prefer Monarch's Data Model Over Pattern Matching

When classifying recurring streams (income, transfer, expense), prefer Monarch's native
data model constructs (category groups, account types) over pattern matching on
user-customized category names. Patterns are fragile — they break when users rename
categories and aren't portable. Category `group.type` (income/transfer/expense) is a
Monarch system-level classification that works universally. See `docs/TODOS.md` A2.

### Persist Only What Monarch Can't Provide

Config should store information Monarch doesn't know: which template a property inherits
from, which bills to remove, who manages a bill, merchant-to-bill links. It should NOT
duplicate data Monarch provides live: amounts, due dates, vendor names, payment status.
These go stale. The config is the human-knowledge layer; Monarch is the live-data layer.

### Stream-to-Property Assignment via Funding Accounts

Each property can have a dedicated bank account (funding_account). When a Monarch stream's
account matches a property's funding account, the stream belongs to that property. This is
deterministic and requires no fuzzy matching. For users with property-specific accounts,
this auto-assigns most streams without user input. For users with shared accounts, streams
fall through to manual classification.

### Bill Configuration

PropertyBill entries are lightweight — most fields are optional. The minimum bill entry is
just a name (inherits everything from the template). Add vendor, merchant_id, managed_by,
remove as needed. Amounts, due dates, and payment status come from Monarch live.

**Alternatives considered and rejected:**

- *Restructuring Monarch categories* to help classify bills. Rejected: couples Monarch's
  tax-reporting category structure to this tool's needs. Not portable across users.

- *Fully automatic bill discovery* with zero config. Rejected: category groups distinguish
  income/transfer/expense but can't distinguish which utility is which within a property.
  Bill-to-merchant linking requires human judgment at least once.

- *has_mortgage as a special flag*. Rejected: mortgage is just another bill. Exclude it
  if the property doesn't have one. No special-case code needed.

- *Separate property_types dict*. Rejected: templates are just abstract properties.
  One inheritance model handles everything.

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
