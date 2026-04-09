"""CLI for bills-agent.

Thin layer providing:
- Launch Claude/Gemini with plugin attached
- Register plugin with Claude/Gemini permanently
- Standalone reports (passthrough to SDK)
"""

import json
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import click

from .sdk.common.config import get_config_path, get_data_dir, load_config


@click.group()
@click.version_option(version="1.1.0")
def main():
    """Bill management for AI agents."""
    pass


# =============================================================================
# Launch Commands
# =============================================================================


@main.command("claude")
@click.option("--prompt", default="check-bills", help="System prompt to use")
def launch_claude(prompt: str):
    """Launch Claude Code with bills plugin attached."""
    # Get plugin path from package
    plugin_path = files("bills") / ".." / "claude" / "plugin"

    # Get prompt path
    prompt_path = files("bills") / ".." / "claude" / "prompts" / f"{prompt}.md"

    if not Path(str(prompt_path)).exists():
        click.echo(f"Prompt not found: {prompt_path}", err=True)
        sys.exit(1)

    prompt_text = Path(str(prompt_path)).read_text()

    cmd = [
        "claude",
        "--system-prompt", prompt_text,
        "--plugin-dir", str(plugin_path),
    ]

    subprocess.run(cmd)


@main.command("gemini")
def launch_gemini():
    """Launch Gemini CLI with bills extension attached."""
    # Get extension path
    extension_path = files("bills") / ".." / "gemini"

    cmd = ["gemini", "--extension", str(extension_path)]
    subprocess.run(cmd)


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
