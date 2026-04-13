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

## Prerequisites

- [Monarch Money](https://www.monarchmoney.com/) account with linked bank accounts
- [monarch-access](https://github.com/krisrowe/monarch-access) MCP server registered in your agent session
- Python 3.11+
- Claude Code CLI installed

> **Note:** Monarch Money is currently the only supported data source. The SDK's
> inventory engine is decoupled from Monarch — it accepts streams and accounts as
> plain data — so the architecture supports alternative providers (other financial
> platforms, local CSV/OFX files, etc.) in the future.

## Quick Start

### 1. Install

```bash
pipx install git+https://github.com/krisrowe/bills-agent.git
```

### 2. Launch

```bash
cd ~/my-finances    # or wherever you keep financial files
bills
```

On first run, `bills` walks you through two one-time choices:

**Agent** — if both Claude Code and Gemini CLI are installed, you pick which one.
If only one is found, it's selected automatically.

**Project directory** — pin the current directory or roam:

```
No project directory configured. Current directory: /home/user/my-finances

  [1] Save this directory (future runs return here)
  [2] Roam (always use whatever directory you're in)

Choice [1/2]:
```

Pick **1** if you have a dedicated folder for financial files — future `bills`
invocations return here automatically, from anywhere. Pick **2** to always launch
from whatever directory you're in.

Both choices are saved to `~/.config/bills/launcher.json` and remembered for
future runs. After that, `bills` is all you type.

### 3. Run your first bill check

```
/bills:check
```

The agent walks you through everything interactively:

- Loads your Monarch recurring streams and account data
- Asks you to declare properties, credit accounts, and expected bills
- Helps link your declarations to Monarch's live data
- Presents a prioritized summary of overdue payments, missing bills, and risks

No manual config is required beforehand. Configuration builds up through
conversation and is saved automatically to `~/.config/bills/config.yaml`.
Each subsequent check is faster as your declarations accumulate.

### 4. Explain a credit card balance

```
/bills:explain
```

Walks through a credit card's statement cycles, charges, payments, and interest
to explain how the current balance was reached. Use anytime — independent of
the bill check workflow.

### Launcher options

```bash
bills                   # uses saved agent + project dir (prompts on first run)
bills --here            # pin to current directory (saves for future runs)
bills --roam            # always use cwd (saves preference)
bills -C /path          # use this directory once (doesn't save)
bills --agent claude    # switch to Claude Code (saves for future runs)
bills --agent gemini    # switch to Gemini CLI (saves for future runs)
bills --non-interactive # fail instead of prompting (for scripts)
```

If the saved directory is moved or deleted, `bills` exits with an error
and a hint to run `--here` from the new location.

## Two Ways to Use the Plugin (Claude Code)

The quick start above uses the `bills` launcher, which loads the plugin directly from
the installed package at launch time. You can also install the plugin persistently through
a Claude Code marketplace. Both give you the same skills, MCP tools, and hooks — they
differ in how the plugin gets loaded and when changes take effect.

### Option A: `bills` launcher (recommended)

```bash
pipx install git+https://github.com/krisrowe/bills-agent.git
bills
```

**What it does:** Detects your agent (Claude Code or Gemini CLI), launches it with
the plugin loaded from the installed package, and pre-approves read-only tools.

| Advantage | Detail |
|-----------|--------|
| **Zero marketplace setup** | One `pipx install`, one command. No marketplace registration, no plugin install steps. |
| **Read-only tools pre-approved** | Account lists, transaction queries, inventory builds, and Monarch reads don't require per-tool approval. Write operations still prompt. |
| **Instant updates** | `pipx install --force git+https://...` and restart. No version bumps, marketplace syncs, or plugin reinstalls. |
| **Development friendly** | Clone the repo, `pip install -e .`, and `bills` pulls directly from your working tree. Edit a skill, restart, changes are live. No commit/push/marketplace cycle. |
| **Remembers your project dir** | Pins to a financial files directory so you can launch from anywhere. |
| **Agent-agnostic** | Works with Claude Code and Gemini CLI. Remembers your choice. |

| Limitation | Detail |
|------------|--------|
| **Session-scoped** | Plugin loads only when launched via `bills`. Opening Claude Code normally won't have it. |
| **Dedicated launcher** | You run `bills` instead of `claude`. If you have other plugins or workflows that launch Claude Code differently, you'd need to incorporate `--plugin-dir` yourself. |

### Option B: Installed plugin (marketplace)

```bash
claude plugin marketplace add https://github.com/<marketplace-repo>.git
claude plugin install bills@<marketplace-name> --scope user
```

| Advantage | Detail |
|-----------|--------|
| **Always available** | Plugin loads in every Claude Code session (user scope) or every session in a project (project scope). No special launcher needed. |
| **Works with other launch methods** | `claude`, IDE extensions, or any workflow that starts Claude Code picks up the plugin automatically. |
| **Scope control** | Install at project scope for a dedicated finances directory, or user scope for global availability. |

| Limitation | Detail |
|------------|--------|
| **Marketplace overhead** | Requires a marketplace repo, registration, and `claude plugin install`. |
| **Update ceremony** | Changes require: version bump in `plugin.json` → commit → push → `claude plugin marketplace update` → `claude plugin update`. |
| **No pre-approved tools** | All tools prompt for approval on first use per session. You can configure allow-lists in `.claude/settings.json` manually. |
| **Plugin also installed?** | If you have the plugin installed *and* run `bills`, `--plugin-dir` takes precedence for that session. No conflicts, but the installed copy is ignored. |

### Which should I use?

**Use `bills`** if you primarily check bills from a terminal and want the
fastest setup and update path. Especially if you're forking or contributing to
the repo — editable installs (`pip install -e .`) mean every code change is live
on the next restart with no publish cycle.

**Use the installed plugin** if you want bills available in every Claude Code session
without thinking about it, or if you use Claude Code through an IDE extension where
a dedicated launcher isn't practical.

**Both at once** works fine. The installed plugin provides ambient availability;
`bills` overrides it with the latest package version and pre-approved tools
when you want a focused bill-checking session.

## What It Includes

- **MCP server** (`bills-mcp`) — manages bill expectations via tools. Works with any MCP-capable agent.
- **Skills** — workflow instructions in the [Agent Skills](https://agentskills.io) open standard:
  - `/bills:check` — full bill review: cross-reference, reconcile, report, triage
  - `/bills:explain` — credit card balance walkthrough
  - `/bills:check-credit-cards` — quick credit card payment verification
- **CLI** (`bills`) — launcher, MCP server registration, and standalone reports.
- **Claude Code plugin** — bundles all of the above plus PostToolUse hooks that cache Monarch API responses to keep the context window clean.

### About PostToolUse hooks

The Claude Code plugin includes hooks that intercept Monarch API responses
(`list_recurring`, `list_accounts`, `list_categories`), extract only the fields
the inventory engine needs, cache to disk, and replace the large response with
a short summary. Monarch responses can be 50-100KB — hooks keep this out of
the agent's context window.

Other platforms don't get hooks. The full responses land in context instead.
This still works — the inventory engine reads from cache files if available, or
the agent can pass data directly. It just uses more context.

## Other Platforms

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

## CLI Reference

### `bills`

Launch your agent with the bills plugin, pre-approved read-only tools, and
project directory management. Auto-detects Claude Code or Gemini CLI.

```bash
bills                         # launch with saved preferences (prompts on first run)
bills --here                  # save current dir, launch from here
bills --roam                  # save roam preference, always use cwd
bills -C ~/finances           # use this dir once (doesn't save)
bills --agent claude          # switch to Claude Code (saves preference)
bills --agent gemini          # switch to Gemini CLI (saves preference)
bills --non-interactive       # fail instead of prompting (for scripts)
bills --prompt <name>         # use a different system prompt (Claude only)
```

Preferences are saved to `~/.config/bills/launcher.json`.

### `bills register`

```bash
bills register claude --scope user     # register in ~/.claude/settings.json
bills register claude --scope project  # register in .claude/settings.local.json
bills register gemini                  # link extension with Gemini CLI
```

### `bills unregister`

```bash
bills unregister claude --scope user
bills unregister claude --scope project
```

### `bills-report`

Standalone reports (no AI agent needed):

```bash
bills-report summary                # config summary: account counts, properties, promos
bills-report summary --format json  # JSON output
bills-report overdue                # overdue detection (stub)
bills-report due-soon               # due-soon detection (stub)
```

## Updating

```bash
pipx install --force git+https://github.com/krisrowe/bills-agent.git
```

Then restart `bills`. Changes take effect immediately.

If using the installed plugin path, also update the plugin:

```bash
claude plugin marketplace update <marketplace-name>
claude plugin update bills@<marketplace-name>
```

Then restart Claude Code. `claude plugin update` only detects changes if the
`version` field in `plugin.json` has been incremented.

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

### Developing with `bills`

An editable install (`pip install -e .`) means `bills` loads the plugin
directly from your working tree. Edit a skill or SDK file, restart the agent,
and the change is live. No commit, push, version bump, or marketplace update needed.

```bash
pip install -e ".[dev]"
bills
```

## License

MIT
