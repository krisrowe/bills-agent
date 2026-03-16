"""Global test configuration - ensures ALL tests are isolated from real config.

All tests run with XDG_CONFIG_HOME pointing to a unique temp directory.
This prevents tests from reading or writing real user config.
"""

import pytest


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Auto-isolate every test from real config directories.

    Creates a unique temp config dir for each test.
    Sets XDG_CONFIG_HOME so get_config_dir() returns the temp path.
    """
    test_config_home = tmp_path / "config"
    test_config_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(test_config_home))


@pytest.fixture
def config_dir(tmp_path):
    """Returns the isolated bills config directory path.

    Use this instead of hardcoding paths.
    """
    return tmp_path / "config" / "bills"
