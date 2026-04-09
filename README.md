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
- **MCP server** (`bills-mcp`) for managing bill expectations via tools
- **CLI** (`bills`) for launching Claude with the plugin, registering the MCP server, and running standalone reports
- **PostToolUse hooks** that automatically cache Monarch API responses to disk, keeping large payloads out of the conversation context

## Prerequisites

- [Monarch Money](https://www.monarchmoney.com/) account with linked bank accounts
- [monarch-access](https://github.com/krisrowe/monarch-access) MCP server registered in your agent session
- Python 3.11+
- An MCP-capable agent platform (Claude Code, Gemini CLI, Cursor, Antigravity, etc.)

## Installation

### 1. Install the package

```bash
pipx install git+https://github.com/krisrowe/bills-agent.git
```

This installs three commands: `bills` (CLI), `bills-mcp` (MCP server), and `bills-report` (standalone reports).

### 2. Register a marketplace that carries this plugin

The plugin installs through a Claude Code marketplace. Check if you already have one registered:

```bash
claude plugin marketplace list
```

If you don't have a marketplace with `bills`, you'll need to add one. See [MARKETPLACE.md](MARKETPLACE.md) for how to add this plugin to a new or existing marketplace.

### 3. Install the plugin

Install into a project directory where you keep bill-related files — receipts, statements, CSVs, financial records, etc. This scopes the plugin's skills and tools to sessions launched from that directory:

```bash
cd ~/my-finances
claude plugin install bills@<marketplace-name> --scope project
```

Alternatively, install at user scope to make the plugin available in every Claude Code session on the machine. This means the skills and MCP tools are always resident regardless of which directory you're working in:

```bash
claude plugin install bills@<marketplace-name> --scope user
```

The plugin provides `/bills:check` and `/bills:explain` skills, the `bills-mcp` MCP server for managing bill expectations, and PostToolUse hooks that cache Monarch data automatically.

### 4. Verify

Start a new Claude Code session (from the project directory if you used `--scope project`) and check:
- `/bills:check` and `/bills:explain` appear as available skills
- `bills-mcp` tools are listed under the plugin's MCP server

### Alternative: Load plugin from a local clone

Useful for development and debugging — loads the plugin directly from your working tree without going through the marketplace. Does not persist across sessions.

```bash
claude --plugin-dir path/to/bills-agent/claude/plugin
```

### Alternative: Any MCP-capable agent platform

The MCP server and skills are not Claude-specific. Any agent platform that supports MCP
can use bills-agent — Gemini CLI, Cursor, Antigravity, or others.

**Step 1: Register the MCP server.** Configure your platform to run `bills-mcp` as a
stdio MCP server. For example, in Gemini CLI (`.gemini/settings.json`):

```json
{
  "mcpServers": {
    "bills": {
      "command": "bills-mcp"
    }
  }
}
```

Or use the built-in CLI helper for supported platforms:

```bash
bills register claude --scope project
bills register gemini
```

**Step 2: Install the skills.** The skill files describe the bill check and
balance explanation workflows. Platforms with native skill support can install
them directly. For Gemini CLI:

```bash
gemini skills install https://github.com/krisrowe/bills-agent.git --path claude/plugin/skills/check
gemini skills install https://github.com/krisrowe/bills-agent.git --path claude/plugin/skills/explain
```

Or link from a local clone for development:

```bash
gemini skills link path/to/bills-agent/claude/plugin/skills/check
gemini skills link path/to/bills-agent/claude/plugin/skills/explain
```

For platforms without a skill install mechanism, load the SKILL.md files into
your agent's context or instruction mechanism. They're plain markdown — copy
them into your project if needed.

**What you don't get without the Claude Code plugin:** PostToolUse hooks. When
installed as a plugin, hooks automatically intercept Monarch API responses
(`list_recurring`, `list_accounts`, `list_categories`), extract only the fields
the inventory engine needs, cache the result to disk, and replace the large MCP
response with a short summary. This keeps the agent's context window clean —
Monarch responses can be 50-100KB of JSON.

Without hooks, the full Monarch responses land in the conversation context. This
still works — the inventory engine reads from the cached files if available, or
the agent can pass data directly. It just uses more context and may require
larger context windows for accounts with many recurring streams.

### Alternative: Cursor and other Agent Skills-compatible platforms

The skills in this repo use the [Agent Skills](https://agentskills.io) open
standard (`SKILL.md` with YAML frontmatter). Platforms that support this standard
can use them directly.

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

**Skills** — Cursor auto-discovers skills from `.claude/skills/` for compatibility,
or you can install from GitHub via Cursor Settings → Rules → Add Rule → Remote Rule.
Point it at this repository.

You can also copy the skill directories into any of the standard skill locations:

```
.agents/skills/       # project-level (Agent Skills standard)
.cursor/skills/       # project-level (Cursor-native)
~/.cursor/skills/     # user-level (global)
```

Each skill is a folder with a `SKILL.md` — the format is the same across all
platforms that support the standard.

### Alternative: Fully manual agent installation

For platforms that don't support Agent Skills or MCP auto-discovery, wire up
two things manually:

**MCP server:** Most MCP-capable platforms use a JSON config with a `mcpServers`
key. Add an entry for `bills-mcp`:

```json
{
  "mcpServers": {
    "bills": {
      "command": "bills-mcp"
    }
  }
}
```

**Skills:** Copy the contents of `claude/plugin/skills/check/SKILL.md` and
`claude/plugin/skills/explain/SKILL.md` into your platform's agent instruction
mechanism — system prompt, rules directory, or equivalent. The skill files are
plain markdown. Only the delivery mechanism is platform-specific.

### Alternative: Register MCP server only (no skills)

If you only need the MCP tools (e.g., you have your own workflow or just want
programmatic access to bill config):

```bash
bills register claude --scope project  # project-scoped (.claude/settings.local.json)
bills register claude                  # user-scoped (~/.claude/settings.json)
```

To unregister:

```bash
bills unregister claude --scope project
bills unregister claude
```

## Quick Start

### 1. Verify monarch-access is working

Before your first bill check, make sure the [monarch-access](https://github.com/krisrowe/monarch-access)
MCP server is registered and can reach your Monarch account. Try calling
`list_accounts` in your agent session — if it returns your bank accounts,
you're good.

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

The `bills` command provides launch helpers, registration, and standalone reports.

### Launch with plugin attached

```bash
bills claude    # launch Claude Code with bills plugin
bills gemini    # launch Gemini CLI with bills extension
```

### Register / unregister MCP server

```bash
bills register claude                  # user-scoped
bills register claude --scope project  # project-scoped
bills register gemini

bills unregister claude
bills unregister claude --scope project
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
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/
```

## License

MIT
