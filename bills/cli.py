"""CLI for bills-agent.

Thin layer providing:
- Launch agent with plugin attached (auto-detects claude/gemini)
- Register plugin with Claude/Gemini permanently
- Standalone reports (passthrough to SDK)
"""

import json
import os
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import click

from .sdk.common.config import get_config_dir, get_config_path, load_config


# =============================================================================
# Saved Preferences
# =============================================================================


def _prefs_path() -> Path:
    """Path to saved launcher preferences."""
    return get_config_dir() / "launcher.json"


def _load_prefs() -> dict:
    """Load launcher preferences."""
    path = _prefs_path()
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _save_prefs(prefs: dict) -> None:
    """Save launcher preferences."""
    path = _prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(prefs, f, indent=2)


def _update_pref(key: str, value: str) -> None:
    """Update a single preference."""
    prefs = _load_prefs()
    prefs[key] = value
    _save_prefs(prefs)


_ROAM_SENTINEL = "."

_SKILL_ALIASES = {
    "cc": "/bills:credit-cards",
    "credit-cards": "/bills:credit-cards",
    "check": "/bills:check",
    "explain": "/bills:explain",
}


def _resolve_initial(value: str) -> str:
    """Resolve an --initial value: skill alias, slash command, or freeform prompt."""
    resolved = _SKILL_ALIASES.get(value)
    if resolved:
        return resolved
    return value


# =============================================================================
# Agent Detection
# =============================================================================


def _agent_command(agent: str) -> str:
    """Resolve the command for an agent.

    Checks BILLS_AGENT_<NAME> env var first (e.g., BILLS_AGENT_CLAUDE).
    Falls back to the agent name itself (claude, gemini).
    """
    return os.environ.get(f"BILLS_AGENT_{agent.upper()}", agent)


def _detect_agents() -> list[str]:
    """Return list of available agent CLIs."""
    agents = []
    if shutil.which(_agent_command("claude")):
        agents.append("claude")
    if shutil.which(_agent_command("gemini")):
        agents.append("gemini")
    return agents


def _resolve_agent(agent_override: str | None, non_interactive: bool) -> str:
    """Resolve which agent to use: override > saved > detect > prompt."""
    if agent_override:
        if not shutil.which(_agent_command(agent_override)):
            click.echo(f"Error: Agent '{agent_override}' not found on PATH.", err=True)
            sys.exit(1)
        _update_pref("agent", agent_override)
        return agent_override

    prefs = _load_prefs()
    saved = prefs.get("agent")
    if saved:
        if not shutil.which(_agent_command(saved)):
            click.echo(
                f"Error: Saved agent '{saved}' not found on PATH.\n"
                f"  Install it or run 'bills --agent claude' or 'bills --agent gemini'.",
                err=True,
            )
            sys.exit(1)
        return saved

    # No saved preference — detect what's available
    available = _detect_agents()

    if len(available) == 0:
        click.echo("Error: Neither 'claude' nor 'gemini' found on PATH.", err=True)
        sys.exit(1)

    if len(available) == 1:
        agent = available[0]
        _update_pref("agent", agent)
        return agent

    # Both available — prompt
    if non_interactive:
        click.echo(
            "Error: Multiple agents available (claude, gemini). No saved preference.\n"
            "  Run 'bills --agent claude' or 'bills --agent gemini' first.",
            err=True,
        )
        sys.exit(1)

    click.echo("Multiple agents found:\n")
    choice = click.prompt(
        "  [1] Claude Code\n"
        "  [2] Gemini CLI\n\n"
        "Choice",
        type=click.Choice(["1", "2"]),
    )
    agent = "claude" if choice == "1" else "gemini"
    _update_pref("agent", agent)
    return agent


# =============================================================================
# Project Directory
# =============================================================================


def _resolve_project_dir(
    directory: str | None, here: bool, roam: bool, non_interactive: bool
) -> str:
    """Resolve project directory: explicit > flags > saved > prompt."""
    if directory:
        project_dir = str(Path(directory).resolve())
        if not Path(project_dir).is_dir():
            click.echo(f"Error: Directory not found: {directory}", err=True)
            sys.exit(1)
        return project_dir

    if roam:
        _update_pref("project_dir", _ROAM_SENTINEL)
        return os.getcwd()

    if here:
        cwd = os.getcwd()
        _update_pref("project_dir", cwd)
        return cwd

    prefs = _load_prefs()
    saved = prefs.get("project_dir")

    if saved == _ROAM_SENTINEL:
        return os.getcwd()

    if saved:
        if not Path(saved).is_dir():
            click.echo(
                f"Error: Saved project directory not found: {saved}\n"
                f"  Run 'bills --here' from your project directory to reset.",
                err=True,
            )
            sys.exit(1)
        return saved

    # First run — prompt
    if non_interactive:
        click.echo(
            "Error: No project directory configured.\n"
            "  Run 'bills --here' or 'bills --roam' first.",
            err=True,
        )
        sys.exit(1)

    cwd = os.getcwd()
    click.echo(f"No project directory configured. Current directory: {cwd}\n")
    choice = click.prompt(
        "  [1] Save this directory (future runs return here)\n"
        "  [2] Roam (always use whatever directory you're in)\n\n"
        "Choice",
        type=click.Choice(["1", "2"]),
    )
    if choice == "1":
        _update_pref("project_dir", cwd)
    else:
        _update_pref("project_dir", _ROAM_SENTINEL)
    return cwd


# =============================================================================
# Agent Launchers
# =============================================================================


def _launch_claude(project_dir: str, user_prompt: str | None = None,
                   print_mode: bool = False):
    """Launch Claude Code with plugin and pre-approved tools."""
    os.chdir(project_dir)

    plugin_path = files("bills") / ".." / "claude" / "plugin"

    # Monarch server name varies by registration. Default "*" uses glob
    # matching. Tests set BILLS_MONARCH_MCP to the exact name (e.g., "monarch")
    # since --bare doesn't support globs in --allowedTools.
    monarch = os.environ.get("BILLS_MONARCH_MCP", "*")

    allowed_tools = [
        # bills-mcp read-only tools (plugin server name: plugin:bills:manager)
        "mcp__plugin_bills_manager__list_*",
        "mcp__plugin_bills_manager__get_*",
        "mcp__plugin_bills_manager__show_*",
        "mcp__plugin_bills_manager__validate_*",
        "mcp__plugin_bills_manager__build_bill_inventory",
        "mcp__plugin_bills_manager__get_inventory_section",
        # monarch-access read-only tools
        f"mcp__{monarch}__list_recurring",
        f"mcp__{monarch}__list_accounts",
        f"mcp__{monarch}__list_categories",
        f"mcp__{monarch}__list_transactions",
    ]

    cmd = [
        _agent_command("claude"),
        "--plugin-dir", str(plugin_path),
    ]
    for tool in allowed_tools:
        cmd.extend(["--allowedTools", tool])

    if user_prompt is not None:
        if print_mode:
            cmd.extend(["-p", user_prompt])
        else:
            cmd.append(user_prompt)

    subprocess.run(cmd)


def _launch_gemini(project_dir: str, user_prompt: str | None = None):
    """Launch Gemini CLI with bills extension."""
    os.chdir(project_dir)

    extension_path = files("bills") / ".." / "gemini"

    cmd = [_agent_command("gemini"), "--extension", str(extension_path)]

    subprocess.run(cmd)


# =============================================================================
# Main CLI
# =============================================================================


@click.group(invoke_without_command=True)
@click.version_option(version="1.1.0")
@click.option("--here", is_flag=True, help="Use current directory as project dir (saves for future runs)")
@click.option("--roam", is_flag=True, help="Always use current directory (saves preference for future runs)")
@click.option("-C", "directory", default=None, help="Use this directory once (doesn't save)")
@click.option("--agent", "agent_override", default=None, type=click.Choice(["claude", "gemini"]),
              help="Use this agent (saves for future runs)")
@click.option("--non-interactive", is_flag=True, help="Fail instead of prompting for input")
@click.option("-p", "print_prompt", default=None, help="Run non-interactively with this prompt (print and exit)")
@click.option("-i", "--initial", default=None, help="Start session with a prompt or skill alias (e.g., cc, check, explain)")
@click.pass_context
def main(ctx, here: bool, roam: bool, directory: str | None,
         agent_override: str | None, non_interactive: bool,
         print_prompt: str | None, initial: str | None):
    """Bill management for AI agents.

    Run without a subcommand to launch your agent with the bills plugin.
    """
    if ctx.invoked_subcommand is not None:
        return

    if print_prompt and initial:
        click.echo("Error: -p and --initial are mutually exclusive.", err=True)
        sys.exit(1)

    agent = _resolve_agent(agent_override, non_interactive)
    project_dir = _resolve_project_dir(directory, here, roam, non_interactive)

    if print_prompt is not None:
        user_prompt = print_prompt
        print_mode = True
    elif initial is not None:
        user_prompt = _resolve_initial(initial)
        print_mode = False
    else:
        user_prompt = None
        print_mode = False

    if agent == "claude":
        _launch_claude(project_dir, user_prompt, print_mode)
    elif agent == "gemini":
        _launch_gemini(project_dir, user_prompt)


# =============================================================================
# Register Commands
# =============================================================================


@main.group("register")
def register_group():
    """Register plugin with agent tools."""
    pass


@register_group.command("claude")
@click.option("--scope", type=click.Choice(["user", "project"]), default="user",
              help="user = ~/.claude/settings.json, project = .claude/settings.local.json")
def register_claude(scope: str):
    """Register bills plugin with Claude Code."""
    if scope == "user":
        settings_path = Path.home() / ".claude" / "settings.json"
    else:
        settings_path = Path.cwd() / ".claude" / "settings.local.json"

    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing settings
    if settings_path.exists():
        with open(settings_path) as f:
            settings = json.load(f)
    else:
        settings = {}

    # Add MCP server
    if "mcpServers" not in settings:
        settings["mcpServers"] = {}

    settings["mcpServers"]["bills"] = {
        "command": "bills-mcp",
    }

    # Save settings
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)

    click.echo(f"Registered bills plugin in {settings_path}")


@register_group.command("gemini")
def register_gemini():
    """Register bills extension with Gemini CLI."""
    extension_path = files("bills") / ".." / "gemini"

    # Link extension
    cmd = ["gemini", "extensions", "link", str(extension_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        click.echo(f"Linked bills extension from {extension_path}")
    else:
        click.echo(f"Failed to link extension: {result.stderr}", err=True)
        sys.exit(1)


@main.group("unregister")
def unregister_group():
    """Unregister plugin from agent tools."""
    pass


@unregister_group.command("claude")
@click.option("--scope", type=click.Choice(["user", "project"]), default="user")
def unregister_claude(scope: str):
    """Unregister bills plugin from Claude Code."""
    if scope == "user":
        settings_path = Path.home() / ".claude" / "settings.json"
    else:
        settings_path = Path.cwd() / ".claude" / "settings.local.json"

    if not settings_path.exists():
        click.echo(f"Settings file not found: {settings_path}")
        return

    with open(settings_path) as f:
        settings = json.load(f)

    if "mcpServers" in settings and "bills" in settings["mcpServers"]:
        del settings["mcpServers"]["bills"]
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)
        click.echo(f"Unregistered bills plugin from {settings_path}")
    else:
        click.echo("bills plugin not registered")


# =============================================================================
# Report Command (Standalone)
# =============================================================================


@click.command("report")
@click.argument("report_type", type=click.Choice(["summary", "overdue", "due-soon"]))
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def report(report_type: str, output_format: str):
    """Generate standalone bill reports (no AI needed)."""
    config = load_config()

    if report_type == "summary":
        result = _summary_report(config)
    elif report_type == "overdue":
        result = _overdue_report(config)
    else:
        result = _due_soon_report(config)

    if output_format == "json":
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(_format_report_text(result))


def _summary_report(config) -> dict:
    """Generate summary report."""
    accounts_with_promo = sum(1 for a in config.credit_accounts if len(a.promos) > 0)
    total_promos = sum(len(a.promos) for a in config.credit_accounts)
    return {
        "credit_accounts": len(config.credit_accounts),
        "accounts_with_promo": accounts_with_promo,
        "total_promo_plans": total_promos,
        "properties": len(config.properties),
        "funding_accounts": len(config.funding_accounts),
        "config_path": str(get_config_path()),
    }


def _overdue_report(config) -> dict:
    """Generate overdue report (stub - needs Monarch integration)."""
    return {"message": "Overdue detection requires Monarch integration (not yet implemented)"}


def _due_soon_report(config) -> dict:
    """Generate due-soon report (stub - needs date calculation)."""
    return {"message": "Due-soon detection requires date calculation (not yet implemented)"}


def _format_report_text(result: dict) -> str:
    """Format report as text."""
    lines = []
    for key, value in result.items():
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
