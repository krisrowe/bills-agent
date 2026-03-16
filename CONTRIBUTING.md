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

bills/mcp/
  server.py       ← MCP tool definitions, calls SDK

bills/
  cli.py          ← CLI commands, calls SDK
```

If you're writing logic in server.py or cli.py, stop and move it to SDK.

### Config Models (Pydantic)

- `PromoFinancing` — a promo plan on a credit account
- `CreditAccount` — a credit account with payment method and promos
- `PropertyBill` — a bill associated with a property
- `Property` — a property with bills
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
│   │   └── SKILL.md         # 5-phase cross-reference workflow
│   └── explain/
│       └── SKILL.md         # CC balance segment walkthrough
```

### Skill: check

Five phases:
1. **Load** — config expectations + Monarch actuals in parallel
2. **Cross-reference** — match expected bills to recurring streams, assess payment status
3. **Investigate** — deeper transaction queries for gaps and anomalies
4. **Summary** — prioritized findings (overdue → promo deadlines → due soon → gaps → all clear)
5. **Resolution** — update config with user-provided info

### Skill: explain

Walks through a credit card's transaction history in segments (between payments/statement dates), showing large charges individually and small charges summarized, with running balance reconciliation.

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
