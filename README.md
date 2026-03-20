# Bills Agent

Track bills that matter — the ones that damage your credit or disconnect essential services. Cross-references your declared expectations against Monarch Money's live recurring data to catch overdue payments, missing bills, and promo financing deadlines.

## Why

Financial apps detect recurring transactions, but they don't know what you *expect* to see. If a mortgage payment stops posting because an account disconnected, Monarch won't alert you — the recurring stream just quietly goes stale. If you own a rental property, you know it should have a mortgage, water, trash, and electric bill every month. If one disappears, that's a problem.

Bills Agent bridges this gap. You declare what bills should exist (properties, credit accounts, expected utilities). The agent cross-references your declarations against Monarch's actual recurring data and flags:

- **Overdue payments** — a bill that should have been paid this cycle wasn't
- **Missing bills** — an expected bill isn't showing up in Monarch at all
- **Untracked obligations** — Monarch sees a consequential bill you haven't declared
- **Promo deadline risks** — deferred interest deadlines approaching (Monarch doesn't track these)
- **Disconnected accounts** — Monarch stopped syncing and you can't see payment status

## What It Includes

- **Claude Code plugin** with `/bills:check` and `/bills:explain` skills
- **MCP server** (`bills-mcp`) for managing bill expectations
- **CLI** (`bills`) for launching Claude with the plugin attached

## Prerequisites

- [Monarch Money](https://www.monarchmoney.com/) account with linked bank accounts
- [monarch-access](https://github.com/krisrowe/monarch-access) MCP server registered in your Claude Code session
- Python 3.11+

## Installation

### Install the package

```bash
pipx install git+https://github.com/krisrowe/bills-agent.git
```

### Install the Claude Code plugin

Add the marketplace and install the plugin:

```bash
claude plugin marketplace add krisrowe/claude-plugins
claude plugin install bills@productivity --scope user
```

Or for development, load directly:

```bash
claude --plugin-dir ~/ws/bills-agent/claude/plugin
```

### Verify

Start Claude Code and check:
- `/bills:check` and `/bills:explain` appear as available skills
- `bills-mcp` tools are listed under the plugin's MCP server

## Quick Start

### 1. Set up bill filters

Bill filters define which Monarch recurring categories are "consequential bills."
Use the `add_bill_filter` tool to add patterns like `*Mortgage*`, `Water`, `Phone`,
`*Insurance*`. Patterns use glob-style matching against Monarch category names.

### 2. Declare your expectations

Use MCP tools to set up your accounts and properties:

- `register_credit_account` — add each credit card/account
- `register_property_bill` — add a property and its bills (creates the property if needed)
- `update_property` — set `inherit` to a template (residence, rental_vacation, etc.)
- `remove_property_bill` — remove inherited bills that don't apply

Properties can inherit from templates. Inheriting from `residence` automatically expects:
Mortgage, Electric/Gas, Water/Trash, Internet, Home Insurance, Property Tax. You only
need to register bills where you're adding vendor details, managed_by, or other overrides.

### 3. Run bill check

```
/bills:check
```

The agent loads your expectations and Monarch's recurring data, cross-references them, investigates gaps, and presents a prioritized summary.

### 4. Explain a balance

```
/bills:explain
```

Walks through a credit card's statement cycles, charges, payments, and interest to explain how the current balance was reached.

## Configuration

All configuration is managed through MCP tools and CLI commands. Your settings are
stored locally and never included in the repo.

### Property Templates

The package ships with templates for common property types:

- **real_estate** — Mortgage, Property Tax
- **residence** (inherits real_estate) — adds Electric/Gas, Water/Trash, Internet, Home Insurance
- **rental_vacation** (inherits real_estate) — adds Electric, Water, Trash, Internet, Insurance, Management
- **rental_longterm** (inherits real_estate) — adds Insurance
- **personal** — Housing, Phone, Auto Insurance

Use `update_property` to set `inherit` on your properties. The inherited template's bills
become your expected bills. Use `remove_property_bill` to remove any that don't apply.
Use `register_property_bill` to add bills beyond the template.

Templates can be chained — rental_vacation inherits from real_estate, so vacation rentals
automatically get Mortgage and Property Tax plus their own bills.


## MCP Tools

### Bill Filters
- `get_bill_filters` — current category patterns
- `set_bill_filters` — replace all patterns
- `add_bill_filter` — add a pattern
- `remove_bill_filter` — remove a pattern

### Credit Accounts
- `list_credit_accounts` — all declared credit accounts
- `get_credit_account` — single account by last4
- `register_credit_account` — add a new account
- `update_credit_account` — update account fields

### Promo Financing
- `list_promo_accounts` — accounts with active 0% financing
- `add_promo` — add a promo plan to an account
- `update_promo` — update promo balance/dates
- `remove_promo` — remove a completed promo

### Properties
- `list_properties` — all properties and their declared bills
- `list_property_bills` — declared bills for one property (inheritance applied)
- `register_property_bill` — add a bill (creates property if needed)
- `update_property_bill` — update bill fields or create local override for inherited bill
- `remove_property_bill` — remove a bill from a property, whether inherited or not
- `update_property` — update property metadata (inherit, abstract, funding_account, etc.)

### Inventory
- `build_bill_inventory` — cross-reference declared bills against bank data, cache result
- `get_inventory_section` — fetch one section from cached inventory, pre-grouped by source

### Ignored Merchants
- `list_ignored_merchants` — merchants you told us to skip
- `add_ignored_merchant` — ignore a bank recurring stream
- `remove_ignored_merchant` — stop ignoring a merchant

### Funding Accounts
- `list_funding_accounts` — checking/savings accounts
- `register_funding_account` — add a funding account

### Config
- `validate_config` — verify config and return summary
- `show_config_path` — show config file location

## Updating

When a new version is released:

```bash
# 1. Update the package (gets latest bills-mcp)
pipx install --force git+https://github.com/krisrowe/bills-agent.git

# 2. Update the marketplace
claude plugin marketplace update productivity

# 3. Update the plugin
claude plugin update bills@productivity

# 4. Restart Claude Code
# IMPORTANT: /reload-plugins is not sufficient for version changes.
# You must exit Claude Code and start a new session for the updated
# plugin to take effect. The old version remains cached until restart.
```

**Note:** `claude plugin update` only detects changes if the `version` field in
`claude/plugin/.claude-plugin/plugin.json` has been incremented. If the version
hasn't changed, Claude Code treats the plugin as up-to-date and skips the update.

## Development

```bash
git clone https://github.com/krisrowe/bills-agent.git
cd bills-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/
```

## License

MIT
