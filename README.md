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

- **MCP server** (`bills-mcp`) — manages bill expectations via tools. Works with any MCP-capable agent.
- **Skills** (`/bills:check`, `/bills:explain`) — workflow instructions in the [Agent Skills](https://agentskills.io) open standard. Portable across platforms.
- **CLI** (`bills`) — launch helpers, MCP server registration, and standalone reports.
- **Claude Code plugin** — bundles all of the above plus PostToolUse hooks that cache Monarch API responses to keep the context window clean.

## Prerequisites

- [Monarch Money](https://www.monarchmoney.com/) account with linked bank accounts
- [monarch-access](https://github.com/krisrowe/monarch-access) MCP server registered in your agent session
- Python 3.11+

> **Note:** Monarch Money is currently the only supported data source. The SDK's
> inventory engine is decoupled from Monarch — it accepts streams and accounts as
> plain data — so the architecture supports alternative providers (other financial
> platforms, local CSV/OFX files, etc.) in the future.

## Setup

Choose your path based on your agent platform:

| Platform | What you get | Section |
|----------|-------------|---------|
| **Claude Code** | Full plugin: skills + MCP server + context-saving hooks | [Claude Code plugin](#claude-code-plugin) |
| **Gemini CLI** | MCP server + skills via `gemini skills install` | [Gemini CLI](#gemini-cli) |
| **Cursor** | MCP server + auto-discovered skills (Agent Skills standard) | [Cursor and Agent Skills](#cursor-and-agent-skills) |
| **Other platforms** | MCP server + skills loaded as agent instructions | [Fully manual](#fully-manual) |
| **MCP tools only** | Just the tools, no skills or hooks — bring your own workflow | [MCP server only](#mcp-server-only) |

All paths start with [installing the package](#1-install-the-package).

## Installation

### 1. Install the package

```bash
pipx install git+https://github.com/krisrowe/bills-agent.git
```

This installs three commands: `bills` (CLI), `bills-mcp` (MCP server), and `bills-report` (standalone reports).

### Claude Code plugin

The plugin bundles skills, MCP server, and PostToolUse hooks that cache Monarch
responses to keep context clean. This is the most complete installation path.

**Register a marketplace** that carries the plugin. Check if you already have one:

```bash
claude plugin marketplace list
```

If you don't have a marketplace with `bills`, see [MARKETPLACE.md](MARKETPLACE.md)
for how to add this plugin to a new or existing marketplace.

**Install the plugin** into a project directory where you keep bill-related files —
receipts, statements, CSVs, financial records, etc.:

```bash
cd ~/my-finances
claude plugin install bills@<marketplace-name> --scope project
```

Or install at user scope to make it available in all sessions:

```bash
claude plugin install bills@<marketplace-name> --scope user
```

**Verify** — start a new Claude Code session and check that `/bills:check` and
`/bills:explain` appear as available skills and `bills-mcp` tools are listed.

**For development** — load the plugin from a local clone without the marketplace.
Does not persist across sessions:

```bash
claude --plugin-dir path/to/bills-agent/claude/plugin
```

### Gemini CLI

**Register the MCP server** in `.gemini/settings.json`:

```json
{
  "mcpServers": {
    "bills": {
      "command": "bills-mcp"
    }
  }
}
```

**Install the skills:**

```bash
gemini skills install https://github.com/krisrowe/bills-agent.git --path claude/plugin/skills/check
gemini skills install https://github.com/krisrowe/bills-agent.git --path claude/plugin/skills/explain
```

Or link from a local clone for development:

```bash
gemini skills link path/to/bills-agent/claude/plugin/skills/check
gemini skills link path/to/bills-agent/claude/plugin/skills/explain
```

### Cursor and Agent Skills

The skills use the [Agent Skills](https://agentskills.io) open standard. Cursor
auto-discovers them and can install directly from GitHub.

**MCP server** — add to `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "bills": {
      "command": "bills-mcp"
    }
  }
}
```

**Skills** — install from GitHub via Cursor Settings → Rules → Add Rule → Remote Rule,
or copy the skill directories into any standard location:

```
.agents/skills/       # project-level (Agent Skills standard)
.cursor/skills/       # project-level (Cursor-native)
~/.cursor/skills/     # user-level (global)
```

Cursor also auto-discovers skills from `.claude/skills/` for compatibility.

### Fully manual

For platforms without native skill or MCP discovery, wire up two things:

**MCP server** — add to your platform's MCP config:

```json
{
  "mcpServers": {
    "bills": {
      "command": "bills-mcp"
    }
  }
}
```

**Skills** — copy `claude/plugin/skills/check/SKILL.md` and
`claude/plugin/skills/explain/SKILL.md` into your platform's agent instruction
mechanism (system prompt, rules directory, etc.). They're plain markdown.

### MCP server only

If you only need the tools without skills or hooks:

```bash
bills register claude --scope project  # project-scoped (.claude/settings.local.json)
bills register claude                  # user-scoped (~/.claude/settings.json)
```

### About PostToolUse hooks

The Claude Code plugin includes hooks that intercept Monarch API responses
(`list_recurring`, `list_accounts`, `list_categories`), extract only the fields
the inventory engine needs, cache to disk, and replace the large response with
a short summary. Monarch responses can be 50-100KB — hooks keep this out of
the agent's context window.

Other platforms don't get hooks. The full responses land in context instead.
This still works — the inventory engine reads from cache files if available, or
the agent can pass data directly. It just uses more context.

## Quick Start

### 1. Verify monarch-access is connected

Try `list_accounts` in your agent session. If it returns your bank accounts, you're good.

### 2. Run your first bill check

```
/bills:check
```

That's it. The agent walks you through everything interactively:

- Loads your Monarch recurring streams and account data
- Asks you to declare properties, credit accounts, and expected bills
- Helps link your declarations to Monarch's live data
- Presents a prioritized summary of overdue payments, missing bills, and risks

No manual setup is required beforehand. Configuration builds up through
conversation and is saved automatically to `~/.config/bills/config.yaml`.
Each subsequent check is faster as your declarations accumulate.

### 3. Explain a credit card balance

```
/bills:explain
```

Walks through a credit card's statement cycles, charges, payments, and interest
to explain how the current balance was reached. Use anytime — independent of
the bill check workflow.

## Configuration

Configuration is managed entirely through MCP tools during agent sessions — you
never need to edit YAML directly. Your settings are stored locally at
`~/.config/bills/config.yaml` and never included in the repo.

### Bill Filters

Bill filters define which Monarch recurring categories count as "consequential bills" —
the ones that damage your credit or disconnect services. Use `add_bill_filter` to add
glob patterns like `*Mortgage*`, `Water`, `Phone`, `*Insurance*`. Patterns match against
Monarch category names (case-insensitive, via `fnmatch`).

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

## CLI

The `bills` command provides launch helpers and standalone reports.

### Launch with plugin attached

```bash
bills claude    # launch Claude Code with bills plugin
```

### Standalone reports (no AI agent needed)

```bash
bills-report summary       # config summary: account counts, properties, promos
bills-report overdue       # overdue detection (stub — needs Monarch integration)
bills-report due-soon      # due-soon detection (stub — needs date calculation)
bills-report summary --format json  # JSON output
```

## Updating

When a new version is released, update the package first, then update the plugin
or skills on your platform.

### Package

```bash
pipx install --force git+https://github.com/krisrowe/bills-agent.git
```

### Claude Code plugin

```bash
claude plugin marketplace update <marketplace-name>
claude plugin update bills@<marketplace-name>
```

Then restart Claude Code. `/reload-plugins` is not sufficient for version changes —
you must exit and start a new session.

**Note:** `claude plugin update` only detects changes if the `version` field in
`claude/plugin/.claude-plugin/plugin.json` has been incremented. If the version
hasn't changed, Claude Code treats the plugin as up-to-date and skips the update.

### Gemini CLI skills

```bash
# If installed from git, reinstall to pick up changes:
gemini skills uninstall check
gemini skills install https://github.com/krisrowe/bills-agent.git --path claude/plugin/skills/check

# If linked from a local clone, changes are picked up automatically.
```

## Development

```bash
git clone https://github.com/krisrowe/bills-agent.git
cd bills-agent
make setup    # prepare venv for testing
make test     # run unit tests (pytest, configured via pytest.ini)
make test-all # run all tests including integration
```

Or manually:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

MIT
