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
  bills/cli.py               ← CLI launcher + register + reports
  claude/plugin/             ← Claude Code plugin
    .claude-plugin/plugin.json
    .mcp.json                 ← points to bills-mcp command
    skills/check/SKILL.md     ← cross-reference workflow
    skills/explain/SKILL.md   ← CC balance walkthrough
    skills/credit-cards/SKILL.md ← deep CC payment verification via transactions

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
├── settings.json            # {"agent": "bills"} — default agent for plugin sessions
├── agents/
│   └── bills.md             # agent definition: ambient context + skill references
├── hooks/
│   ├── hooks.json           # PostToolUse hook definitions
│   └── cache_monarch.py     # intercepts Monarch responses, caches to disk
├── skills/                    # Agent Skills standard (agentskills.io)
│   ├── check/
│   │   └── SKILL.md         # 4-phase: load → reconcile → report → triage
│   └── explain/
│       └── SKILL.md         # CC balance segment walkthrough
```

### Agent Definition

The plugin declares a default agent via `settings.json` → `{"agent": "bills"}`,
which points to `agents/bills.md`. This file provides ambient context to every
session — tool descriptions, priority guidance, output preferences — without
replacing Claude Code's default system prompt.

This works for both launch paths: `bills` launcher and installed plugin. Previous
versions used `--system-prompt` in the launcher, which **replaced** Claude Code's
entire default system prompt. The agent definition layers on top instead.

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

The `bills` CLI (`bills/cli.py`) is the unified launcher and management tool.
It is a thin wrapper — no business logic.

### Launcher (`bills` with no subcommand)

Running `bills` with no subcommand launches an agent (Claude Code or Gemini CLI)
with the plugin attached, pre-approved read-only tools, and a managed project directory.

**Agent detection:** On first run, `bills` checks which agent CLIs are on PATH
via `shutil.which`. If only one is found, it's selected automatically. If both
are found, the user picks interactively. The choice is saved to
`~/.config/bills/launcher.json` and reused on subsequent runs. `--agent claude`
or `--agent gemini` overrides and saves the preference.

**Project directory:** On first run, the user chooses to pin the current directory
or roam. Pinned means `bills` always `os.chdir()` to the saved path before launching.
Roam means it uses whatever cwd the caller is in. `--here` pins to cwd, `--roam`
enables roaming, `-C <dir>` overrides once without saving.

**Pre-approved tools:** The Claude launcher passes `--allowedTools` for read-only
tools from both `bills-mcp` and `monarch-access`, so data loading doesn't require
per-tool approval. Write operations still prompt. This is the only way to
pre-approve tools at launch — Claude Code plugins cannot declare allowed tools
in their configuration, and the alternative is manually editing `.claude/settings.json`.

**Agent command substitution:** For testing, set `BILLS_AGENT_CLAUDE` or
`BILLS_AGENT_GEMINI` to override the command used. Tests point these to a fake
agent script that records its args and exits. See `tests/unit/test_cli_launcher.py`.

### Subcommands

| Command | Description |
|---------|-------------|
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

### Preferences file

`~/.config/bills/launcher.json` stores:
- `agent` — `"claude"` or `"gemini"`
- `project_dir` — absolute path or `"."` (roam sentinel)

## Development Loop

### Testing locally (no commit/push needed)

With an editable install (`pip install -e .`), `bills` loads the plugin directly
from your working tree. Edit a skill or SDK file, restart the agent, and the
change is live.

```bash
pip install -e ".[dev]"
bills
```

For SDK/MCP code changes that affect the installed `bills-mcp` command (e.g.,
new tools, model changes), reinstall:

```bash
pipx install --force .
bills
```

### Debugging launcher behavior

When investigating behavior observed in a Claude Code session (e.g., a tool not
being pre-approved, wrong plugin path, missing flags), use `-p` to run a prompt
non-interactively from a temp directory:

```bash
# Run a specific prompt without going interactive
bills -p "list my credit card accounts" -C /tmp/test-bills

# Test from a fresh project dir
mkdir /tmp/test-bills && bills -p "/bills:credit-cards" -C /tmp/test-bills
```

The `-p` flag passes through to `claude -p`, which runs the prompt, prints the
response, and exits. This lets you test the full launcher pipeline — plugin
loading, tool pre-approval, agent context — without opening an interactive
session. Especially useful for verifying that `--allowedTools` patterns match
what Claude Code actually resolves at runtime (server names vary by how
monarch-access is registered).

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

### The Claude Plugin Lives Inside the Python Package

The Claude plugin (`bills/plugin/`) is a subdirectory of the `bills` Python
package — not a sibling at the repo root. This is deliberate so the plugin
ships with `pipx install`. When `bills` launches Claude Code, it points
`--plugin-dir` at `files("bills") / "plugin"`, which resolves to the
installed pipx location (or the working tree for editable installs).

**Gotchas to watch for:**

- **Don't move the plugin back to a repo-root location.** Putting it at
  `claude/plugin/` outside `bills/` breaks pipx installs — the plugin files
  don't ship because only `bills*` packages are included.

- **Dotfiles require explicit patterns in `package-data`.** Setuptools'
  `**/*` glob does NOT match dotfiles, so `.claude-plugin/plugin.json` and
  `.mcp.json` get silently dropped from the wheel. The current config
  enumerates them explicitly:
  ```toml
  "bills.plugin" = ["**/*", ".*", ".claude-plugin/*", ".mcp.json"]
  ```
  If you add more dotfiles to the plugin, update this pattern.

- **`__init__.py` is required** in `bills/plugin/` so setuptools treats it
  as a Python package and includes it in `find_packages`.

- **Hooks reference `${CLAUDE_PLUGIN_ROOT}`** which Claude Code sets at
  runtime to wherever `--plugin-dir` points. This resolves correctly whether
  the plugin is loaded from a working tree (dev) or pipx site-packages
  (prod) — no path fixup needed.

- **After changing the plugin structure**, always verify with a fresh
  `pipx install --force .` followed by `ls ~/.local/pipx/venvs/bills-agent/lib/python*/site-packages/bills/plugin/`
  to confirm the expected files actually shipped.


## Testing

- `python -m pytest tests/` runs all unit tests
- Tests are isolated via `XDG_CONFIG_HOME` fixture — no real config touched
- Sociable unit tests — no mocks, real config read/write to temp dirs
- Test names describe scenario + outcome, not implementation
- **CLI launcher tests** (`test_cli_launcher.py`) use `BILLS_AGENT_CLAUDE` /
  `BILLS_AGENT_GEMINI` env vars to substitute a fake agent script that records
  its args and exits. No real agent is ever invoked. See "Agent command
  substitution" in the CLI section above.

### Claude Code integration tests

`tests/claude/` tests launch the real Claude Code binary with `--bare` and `-p`
to verify end-to-end plugin behavior. They follow the same sociable testing
philosophy as unit tests — no mocks — except the external dependency is Claude
Code itself rather than file I/O.

**How they work:** Each test calls `claude --bare --plugin-dir <plugin> --mcp-config <fake> -p "prompt"`.
`--bare` ensures a clean session — no user hooks, CLAUDE.md, auto-memory, or
other plugins. The only MCP servers are `bills-mcp` (via plugin) and
`fake_monarch.py` (via `--mcp-config`). The fake server is a ~30-line FastMCP
stdio script that returns canned account data.

**What they test:**
- Plugin loads and MCP tools register correctly
- `--allowedTools` patterns actually pre-approve the intended tools
- Agent can call tools and return meaningful output from a prompt

**What they don't test:**
- PostToolUse hooks — `--bare` disables all hooks. Hook behavior (Monarch
  response caching, context compression) needs manual verification.
- Non-deterministic output — assertions check for signals (tool was called,
  data appeared), not exact strings.

**Requirements:** `claude` on PATH, `ANTHROPIC_API_KEY` set. Each test makes
a real API call. Excluded from default `pytest` runs via `testpaths` in
`pytest.ini`.

## Data Privacy

This repo is PUBLIC. All personal data lives in `~/.config/bills/` at runtime, never in the repo. Use generic examples only in code, tests, and documentation.

## Design Principles

### Fix the Source, Not the Filter

When Monarch data is wrong (stale recurring streams, phantom entries), the correct response is to fix Monarch — not to add exclusions or workarounds in the config. The bill filter is intentionally inclusive: if something matches, it's treated as a real bill.

### Documentation Standards

#### Three audiences, one source of truth

- **Users** (human) reading docs to install, configure, and use the tool
- **User-facing agents** reading skills and agent definitions to operate the tool on the user's behalf
- **Contributor agents** (and human contributors) reading README + CONTRIBUTING to understand the product before modifying it

README is the single source of truth for what the product does, how it works from
a user perspective, and what commitments we've made about behavior. It serves all
three audiences — users read it to learn the tool, user-facing agents reference
it indirectly through skills that align with it, and contributor agents load it
directly into context (via `CLAUDE.md` / `.gemini/settings.json`). Most README
content is relevant to contributors because it's the only place that declares
user-facing intentions — what should this do, what did we promise, what's the
vision.

CONTRIBUTING supplements README with internal knowledge: how the code is
organized, why decisions were made, how to test and release. It should not
duplicate what the product does functionally — that's README's job. A
contributor agent gets both files in context, so repeating README content in
CONTRIBUTING just wastes tokens and creates drift risk. When CONTRIBUTING
needs to reference a user-facing concept, point to README rather than
restating it.

#### Where things live

| File | Audience | Purpose | Level of detail |
|------|----------|---------|-----------------|
| `README.md` | Users, contributors, contributor agents | Product truth: what it does functionally, how to use it, user commitments, skill overview, config concepts, CLI and tool reference | Concise but authoritative. The canonical answer to "how is this supposed to be used?" Links to `docs/` for depth on specific topics. |
| `docs/*.md` | Users, contributors | Detailed topic guides — scenarios, troubleshooting, data model quirks | Thorough. Real examples of what goes wrong and how to fix it. Organized by topic, not by code structure. |
| `claude/plugin/agents/bills.md` | User-facing agents | Ambient session context — tool inventory, skill selection, common data problems and workarounds | Operational. Written as guidance the agent applies in real-time. Scenarios describe what the agent will encounter and what to do about it. |
| `claude/plugin/skills/*/SKILL.md` | User-facing agents | Step-by-step workflow for a specific task — phases, tool calls, presentation rules | Prescriptive. The agent follows these as a recipe. Frontmatter description explains when to invoke vs. alternatives. |
| `CONTRIBUTING.md` | Contributors, contributor agents | Architecture, design decisions, code organization, testing, release process, these standards | Internal. How the code works and why. Supplements README — does not duplicate it. |

#### Ordering within README

1. **Why** — the problem this solves (motivation before mechanics)
2. **Prerequisites** — what you need before installing
3. **Quick Start** — install, launch, first use (get to value fast)
4. **Usage** — skills overview, example prompts, when to use which, links to detailed docs
5. **Installation options** — alternative install paths (plugin, marketplace, manual)
6. **What It Includes** — components list (MCP server, skills, CLI, hooks)
7. **Other Platforms** — Gemini, Cursor, manual setup
8. **Configuration** — config concepts, templates, filters (how it works, not raw YAML)
9. **MCP Tools** — tool reference grouped by domain
10. **CLI Reference** — command-line usage
11. **Updating** — how to get new versions
12. **Development** — contributing, testing, editable install

#### Ordering within CONTRIBUTING

1. **What It Does** — one-paragraph product summary for orientation
2. **Design Goals** — principles that govern decisions
3. **Architecture** — where things live, data flow, two-layer config
4. **Plugin Structure** — agent definition, skills, hooks, settings
5. **CLI** — launcher, subcommands, preferences
6. **Development Loop** — local testing, debugging, releasing
7. **Testing** — test philosophy and patterns
8. **Data Privacy** — what's safe to commit
9. **Design Principles** — detailed rationale for specific decisions
10. **Future Enhancements** — known gaps

#### Overlap between agent/skill content and human docs

Once installed as a plugin, the repo's README is not loaded into the agent's
context. The agent only sees the agent definition and skill files. Conversely,
a human user may never see the agent `.md` files — they read the README and
docs. These two audiences are completely separated at runtime, so both need to
independently cover workflow guidance: which skill to use in which scenario,
what data problems to expect, how to work around issues.

The key distinction is voice, not content:
- **Agent files** (`agents/bills.md`, skill frontmatter): operational.
  "When you see X, do Y. If `/bills:check` shows Z, suggest `/bills:credit-cards`."
- **Human docs** (`README.md`, `docs/*.md`): explanatory.
  "Here's what can go wrong, here's why, here's how to fix it or work around it."

Both may describe the same scenarios. That's fine — they serve readers who will
never see the other surface.

When adding a new scenario or data problem:
1. Add it to the relevant `docs/*.md` file with full explanation
2. Add the operational version to `agents/bills.md` (what to do about it)
3. If it affects skill selection, update the skill frontmatter descriptions
4. If it's a common first-encounter issue, mention it briefly in README's
   Usage section with a link to the detailed doc

#### Skill frontmatter descriptions

Skill `description` fields serve double duty: they help the agent decide which
skill to invoke, and they appear in slash-command listings. Write them as:

- **What** the skill does (one sentence)
- **When** to use it vs. alternatives (the rest)

Focus the "when" on observable conditions — things the agent or user can see
that indicate this skill is the right choice. Not abstract ("when config is
incomplete") but concrete ("when recurring streams aren't matched to accounts,
last paid dates are lagging, or autopay merchant names are too generic to link").

#### `docs/` organization

One file per topic. Name files after the topic, not the skill or component:
- `docs/credit-cards.md` — not `docs/credit-cards-skill.md`
- `docs/promo-financing.md` — not `docs/promo-tool-usage.md`

Each doc should be self-contained enough that a human can read it without
having read the README first, but should not duplicate installation or
quick-start material.

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
Monarch system-level classification that works universally. See
[Monarch Default Categories](docs/monarch/categories.md) for the full default
taxonomy and why relying on group types (not category names) is portable across
users; and [Design TODOs](docs/TODOS.md) item A2 for the ongoing work to apply
this principle consistently across stream classification paths.

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

### Prerequisite Verification

The `bills` launcher handles project directory management and tool pre-approval,
but doesn't verify that `monarch-access` is installed and reachable. A future
enhancement could check for `monarch-mcp` on PATH at launch time and offer to
install it if missing.
