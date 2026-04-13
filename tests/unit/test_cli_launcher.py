"""Tests for the bills CLI launcher — agent detection, project dir, and launch paths.

Uses a fake agent script that records args to a file and exits,
substituted via the BILLS_AGENT_CLAUDE / BILLS_AGENT_GEMINI env vars
that cli.py already supports. No real agent is ever invoked.
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def fake_agent(tmp_path):
    """Create a fake agent script that records its args and exits.

    Returns the path to the script. Set BILLS_AGENT_CLAUDE or
    BILLS_AGENT_GEMINI to this path in tests.
    """
    record_file = tmp_path / "agent_invocation.json"
    script = tmp_path / "fakeagent"
    script.write_text(
        f"#!/usr/bin/env python3\n"
        f"import json, sys, os\n"
        f"json.dump({{'args': sys.argv[1:], 'cwd': os.getcwd()}}, "
        f"open({str(record_file)!r}, 'w'))\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script), record_file


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """Isolate XDG dirs and HOME so no real config is touched."""
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    home_dir = tmp_path / "home"
    config_dir.mkdir(exist_ok=True)
    data_dir.mkdir(exist_ok=True)
    home_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_dir))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_dir))
    monkeypatch.setenv("HOME", str(home_dir))
    return config_dir, data_dir, home_dir


def _run_bills(*args, env_override=None):
    """Run the bills CLI as a subprocess, return CompletedProcess."""
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    return subprocess.run(
        [sys.executable, "-m", "bills.cli"] + list(args),
        capture_output=True, text=True, env=env, timeout=10,
    )


_REPO_ROOT = str(Path(__file__).resolve().parents[2])


def _run_bills_with_fake(fake_agent, isolated_env, extra_args=None,
                          agent="claude", extra_env=None, cwd=None):
    """Run bills with a fake agent, return (result, invocation_record)."""
    script_path, record_file = fake_agent
    config_dir, _, home_dir = isolated_env

    env = os.environ.copy()
    env[f"BILLS_AGENT_{agent.upper()}"] = script_path
    env["XDG_CONFIG_HOME"] = str(config_dir)
    env["HOME"] = str(home_dir)
    env["PYTHONPATH"] = _REPO_ROOT
    # Make sure only our fake agent is "found"
    if agent == "claude":
        env["BILLS_AGENT_GEMINI"] = "/nonexistent/gemini"
    else:
        env["BILLS_AGENT_CLAUDE"] = "/nonexistent/claude"
    if extra_env:
        env.update(extra_env)

    args = list(extra_args or [])
    # Always non-interactive to avoid prompts in tests
    if "--non-interactive" not in args:
        args.append("--non-interactive")

    result = subprocess.run(
        [sys.executable, "-m", "bills.cli"] + args,
        capture_output=True, text=True, env=env, timeout=10,
        cwd=cwd,
    )

    invocation = None
    if record_file.exists():
        invocation = json.loads(record_file.read_text())

    return result, invocation


# =============================================================================
# Agent Detection
# =============================================================================


class TestAgentDetection:
    def test_auto_detects_single_agent(self, fake_agent, isolated_env, tmp_path):
        """When only one agent is on PATH, it's selected automatically."""
        result, invocation = _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["--here"],  # satisfy project dir requirement
        )
        assert result.returncode == 0
        assert invocation is not None, "Fake agent was not invoked"

    def test_agent_override_selects_agent(self, fake_agent, isolated_env):
        result, invocation = _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["--agent", "claude", "--here"],
        )
        assert result.returncode == 0
        assert invocation is not None

    def test_agent_override_saves_preference(self, fake_agent, isolated_env):
        config_dir, _, _ = isolated_env
        _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["--agent", "claude", "--here"],
        )
        prefs = json.loads((config_dir / "bills" / "launcher.json").read_text())
        assert prefs["agent"] == "claude"

    def test_no_agents_available_fails(self, isolated_env, tmp_path):
        config_dir, _, home_dir = isolated_env
        env = os.environ.copy()
        env["BILLS_AGENT_CLAUDE"] = "/nonexistent/claude"
        env["BILLS_AGENT_GEMINI"] = "/nonexistent/gemini"
        env["XDG_CONFIG_HOME"] = str(config_dir)
        env["HOME"] = str(home_dir)
        # Override PATH to exclude real agents
        env["PATH"] = str(tmp_path)

        result = subprocess.run(
            [sys.executable, "-m", "bills.cli", "--non-interactive", "--here"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode != 0
        assert "not found" in result.stderr.lower() or "neither" in result.stderr.lower()

    def test_saved_agent_not_on_path_fails(self, fake_agent, isolated_env):
        config_dir, _, _ = isolated_env
        # Save a preference for an agent that doesn't exist
        prefs_dir = config_dir / "bills"
        prefs_dir.mkdir(parents=True, exist_ok=True)
        (prefs_dir / "launcher.json").write_text(
            json.dumps({"agent": "claude", "project_dir": "."})
        )
        # Now make claude unavailable
        env = os.environ.copy()
        env["BILLS_AGENT_CLAUDE"] = "/nonexistent/claude"
        env["BILLS_AGENT_GEMINI"] = "/nonexistent/gemini"
        env["XDG_CONFIG_HOME"] = str(config_dir)
        env["PATH"] = "/usr/bin:/bin"  # exclude real agents

        result = subprocess.run(
            [sys.executable, "-m", "bills.cli", "--non-interactive"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()


# =============================================================================
# Project Directory
# =============================================================================


class TestProjectDir:
    def test_here_saves_cwd_and_agent_lands_there(self, fake_agent, isolated_env, tmp_path):
        """--here saves caller's cwd as project dir; agent chdir's to it."""
        config_dir, _, _ = isolated_env
        caller_dir = tmp_path / "my_finances"
        caller_dir.mkdir()

        result, invocation = _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["--here"],
            cwd=str(caller_dir),
        )
        assert result.returncode == 0
        prefs = json.loads((config_dir / "bills" / "launcher.json").read_text())
        assert prefs["project_dir"] == str(caller_dir)
        assert invocation["cwd"] == str(caller_dir)

    def test_roam_uses_caller_cwd(self, fake_agent, isolated_env, tmp_path):
        """--roam saves sentinel; agent lands in whatever cwd caller used."""
        config_dir, _, _ = isolated_env
        caller_dir = tmp_path / "wherever"
        caller_dir.mkdir()
        result, invocation = _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["--roam"],
            cwd=str(caller_dir),
        )
        assert result.returncode == 0
        prefs = json.loads((config_dir / "bills" / "launcher.json").read_text())
        assert prefs["project_dir"] == "."
        assert invocation["cwd"] == str(caller_dir)

    def test_explicit_dir_differs_from_caller(self, fake_agent, isolated_env, tmp_path):
        """-C sends agent to a different dir than caller's cwd."""
        caller_dir = tmp_path / "caller_here"
        project_dir = tmp_path / "project_there"
        caller_dir.mkdir()
        project_dir.mkdir()
        result, invocation = _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["-C", str(project_dir)],
            cwd=str(caller_dir),
        )
        assert result.returncode == 0
        assert invocation["cwd"] == str(project_dir)

    def test_explicit_directory_not_saved(self, fake_agent, isolated_env, tmp_path):
        config_dir, _, _ = isolated_env
        target = tmp_path / "explicit_dir"
        target.mkdir()
        _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["-C", str(target)],
        )
        prefs_path = config_dir / "bills" / "launcher.json"
        if prefs_path.exists():
            prefs = json.loads(prefs_path.read_text())
            assert prefs.get("project_dir") != str(target)

    def test_nonexistent_directory_fails(self, fake_agent, isolated_env, tmp_path):
        result, _ = _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["-C", str(tmp_path / "nope")],
        )
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()

    def test_saved_dir_gone_fails(self, fake_agent, isolated_env, tmp_path):
        config_dir, _, _ = isolated_env
        gone_dir = tmp_path / "was_here"
        gone_dir.mkdir()
        # Save it as preference
        prefs_dir = config_dir / "bills"
        prefs_dir.mkdir(parents=True, exist_ok=True)
        (prefs_dir / "launcher.json").write_text(
            json.dumps({"agent": "claude", "project_dir": str(gone_dir)})
        )
        # Remove it
        gone_dir.rmdir()

        result, _ = _run_bills_with_fake(
            fake_agent, isolated_env,
        )
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()
        assert "--here" in result.stderr

    def test_no_project_dir_non_interactive_fails(self, fake_agent, isolated_env):
        result, _ = _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=[],  # no --here, --roam, or -C
        )
        assert result.returncode != 0
        assert "no project directory" in result.stderr.lower()


# =============================================================================
# Launch — Claude
# =============================================================================


class TestLaunchClaude:
    def test_passes_plugin_dir(self, fake_agent, isolated_env):
        result, invocation = _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["--here"],
        )
        assert "--plugin-dir" in invocation["args"]
        idx = invocation["args"].index("--plugin-dir")
        plugin_dir = invocation["args"][idx + 1]
        assert "claude" in plugin_dir and "plugin" in plugin_dir

    def test_passes_allowed_tools(self, fake_agent, isolated_env):
        result, invocation = _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["--here"],
        )
        assert "--allowedTools" in invocation["args"]
        allowed_count = invocation["args"].count("--allowedTools")
        assert allowed_count > 0

    def test_p_flag_passes_prompt_to_agent(self, fake_agent, isolated_env):
        """bills -p 'some prompt' passes -p and the prompt to claude."""
        result, invocation = _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["--here", "-p", "list my credit cards"],
        )
        assert result.returncode == 0
        assert "-p" in invocation["args"]
        idx = invocation["args"].index("-p")
        assert invocation["args"][idx + 1] == "list my credit cards"

    def test_no_p_flag_launches_interactive(self, fake_agent, isolated_env):
        """Without -p, no -p flag is passed to the agent."""
        result, invocation = _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["--here"],
        )
        assert result.returncode == 0
        assert "-p" not in invocation["args"]


# =============================================================================
# Preference Persistence
# =============================================================================


class TestPreferencePersistence:
    def test_second_run_uses_saved_prefs(self, fake_agent, isolated_env, tmp_path):
        """After first run with --here, second run launches to saved dir
        even when caller is somewhere else."""
        config_dir, _, _ = isolated_env
        project_dir = tmp_path / "finances"
        caller_dir = tmp_path / "somewhere_else"
        project_dir.mkdir()
        caller_dir.mkdir()

        _, record_file = fake_agent

        # First run — from project dir, save prefs
        _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["--here"],
            cwd=str(project_dir),
        )

        # Clear record
        record_file.unlink(missing_ok=True)

        # Second run — from a different dir, no flags
        result, invocation = _run_bills_with_fake(
            fake_agent, isolated_env,
            cwd=str(caller_dir),
        )
        assert result.returncode == 0
        assert invocation["cwd"] == str(project_dir)

    def test_here_overrides_roam(self, fake_agent, isolated_env, tmp_path):
        """--here after --roam exits roam mode and pins to cwd."""
        config_dir, _, _ = isolated_env
        pin_dir = tmp_path / "pin_here"
        pin_dir.mkdir()

        _, record_file = fake_agent

        # First: set roam
        _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["--roam"],
        )
        prefs = json.loads((config_dir / "bills" / "launcher.json").read_text())
        assert prefs["project_dir"] == "."

        record_file.unlink(missing_ok=True)

        # Second: pin with --here
        _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["--here"],
            cwd=str(pin_dir),
        )
        prefs = json.loads((config_dir / "bills" / "launcher.json").read_text())
        assert prefs["project_dir"] == str(pin_dir)


# =============================================================================
# Launch — Gemini
# =============================================================================


class TestLaunchGemini:
    def test_gemini_passes_extension_flag(self, fake_agent, isolated_env):
        """Gemini launch uses --extension with the gemini extension path."""
        result, invocation = _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["--agent", "gemini", "--here"],
            agent="gemini",
        )
        assert result.returncode == 0
        assert invocation is not None, "Fake agent was not invoked"
        assert "--extension" in invocation["args"]

    def test_gemini_lands_in_project_dir(self, fake_agent, isolated_env, tmp_path):
        """Gemini agent starts in the resolved project directory."""
        project_dir = tmp_path / "gemini_finances"
        project_dir.mkdir()
        result, invocation = _run_bills_with_fake(
            fake_agent, isolated_env,
            extra_args=["--agent", "gemini", "--here"],
            agent="gemini",
            cwd=str(project_dir),
        )
        assert result.returncode == 0
        assert invocation["cwd"] == str(project_dir)
