"""Fake Monarch Money MCP server for integration testing.

Returns canned data for list_accounts, list_recurring, and list_categories.
Runs as stdio — launched by Claude Code via --mcp-config.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fake-monarch")


@mcp.tool()
def list_accounts() -> dict:
    """List financial accounts."""
    return {"accounts": [
        {
            "id": "test-cc-001",
            "displayName": "Test Rewards Card",
            "mask": "4567",
            "currentBalance": 1250.00,
            "type": {"name": "credit_card"},
            "credential": {"updateRequired": False},
            "institution": {"name": "Test Bank"},
        },
        {
            "id": "test-checking-001",
            "displayName": "Test Checking",
            "mask": "8901",
            "currentBalance": 5000.00,
            "type": {"name": "depository"},
            "credential": {"updateRequired": False},
            "institution": {"name": "Test Bank"},
        },
    ]}


@mcp.tool()
def list_recurring() -> dict:
    """List recurring transactions."""
    return {"recurring": []}


@mcp.tool()
def list_categories() -> dict:
    """List transaction categories."""
    return {"categories": []}


@mcp.tool()
def list_transactions(
    account_ids: list[str] | None = None,
    start_date: str | None = None,
    limit: int = 20,
    search: str | None = None,
) -> dict:
    """List transactions."""
    return {"transactions": []}


if __name__ == "__main__":
    mcp.run(transport="stdio")
