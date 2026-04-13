"""PostToolUse hook: cache Monarch data to disk in canonical form.

Intercepts list_recurring and list_accounts responses, extracts only the
fields build_bill_inventory needs, writes to XDG data dir, and replaces
the large MCP response with a short summary.

Usage (from hooks.json):
  python3 claude/plugin/hooks/cache_monarch.py recurring
  python3 claude/plugin/hooks/cache_monarch.py accounts
"""

import json
import os
import sys
from pathlib import Path

CACHE_DIR = Path(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))) / "bills"

RECURRING_FIELDS = {
    "stream_id", "merchant_id", "merchant", "amount", "actual_amount",
    "frequency", "category", "account", "account_id", "is_past",
    "transaction_id", "due_date", "last_paid_date",
}

ACCOUNT_FIELDS = {"id", "displayName", "mask", "type", "currentBalance", "credential", "institution"}


def extract_data(hook_input: dict) -> list[dict]:
    """Extract the actual data from the MCP tool response structure."""
    response = hook_input.get("tool_response", {})

    # Response can be a JSON string, a dict, or a list of content blocks
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            return []

    if isinstance(response, dict):
        for key in ("recurring", "accounts", "categories"):
            if key in response:
                return response[key]
        return [response]

    if isinstance(response, list):
        # Content blocks: [{"type": "text", "text": "{...}"}]
        for block in response:
            if isinstance(block, dict) and block.get("type") == "text":
                try:
                    parsed = json.loads(block["text"])
                    if isinstance(parsed, dict):
                        for key in ("recurring", "accounts", "categories"):
                            if key in parsed:
                                return parsed[key]
                    return parsed if isinstance(parsed, list) else [parsed]
                except (json.JSONDecodeError, TypeError):
                    continue
        return response

    return []


def canonicalize_recurring(items: list[dict]) -> list[dict]:
    """Keep only fields the inventory SDK uses."""
    return [{k: item.get(k) for k in RECURRING_FIELDS} for item in items]


def canonicalize_accounts(items: list[dict]) -> list[dict]:
    """Keep only fields the inventory SDK uses, flatten nested objects."""
    result = []
    for item in items:
        acct = {
            "id": item.get("id"),
            "displayName": item.get("displayName"),
            "mask": item.get("mask"),
            "type": {"name": (item.get("type") or {}).get("name")},
            "currentBalance": item.get("currentBalance"),
            "credential": {
                "updateRequired": (item.get("credential") or {}).get("updateRequired", False),
            },
            "institution": {
                "name": (item.get("institution") or {}).get("name"),
            },
        }
        result.append(acct)
    return result


def canonicalize_categories(items: list[dict]) -> list[dict]:
    """Keep only fields needed for category group classification."""
    return [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "group": {
                "name": (item.get("group") or {}).get("name"),
                "type": (item.get("group") or {}).get("type"),
            },
        }
        for item in items
    ]


def main():
    resource_type = sys.argv[1] if len(sys.argv) > 1 else None

    if resource_type not in ("recurring", "accounts", "categories"):
        sys.exit(0)

    hook_input = json.load(sys.stdin)
    items = extract_data(hook_input)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if resource_type == "recurring":
        canonical = canonicalize_recurring(items)
        cache_file = CACHE_DIR / "monarch_recurring.json"
        cache_file.write_text(json.dumps(canonical))
        output = {
            "recurring": {
                "count": len(canonical),
                "cached": str(cache_file),
            }
        }

    elif resource_type == "accounts":
        canonical = canonicalize_accounts(items)
        cache_file = CACHE_DIR / "monarch_accounts.json"
        cache_file.write_text(json.dumps(canonical))
        output = {
            "accounts": {
                "count": len(canonical),
                "credit": sum(1 for a in canonical if (a.get("type") or {}).get("name") == "credit"),
                "loan": sum(1 for a in canonical if (a.get("type") or {}).get("name") == "loan"),
                "credential_issues": sum(1 for a in canonical if (a.get("credential") or {}).get("updateRequired")),
                "cached": str(cache_file),
            }
        }

    elif resource_type == "categories":
        canonical = canonicalize_categories(items)
        cache_file = CACHE_DIR / "monarch_categories.json"
        cache_file.write_text(json.dumps(canonical))
        groups = {}
        for c in canonical:
            g = (c.get("group") or {}).get("type", "unknown")
            groups[g] = groups.get(g, 0) + 1
        output = {
            "categories": {
                "count": len(canonical),
                "by_group_type": groups,
                "cached": str(cache_file),
            }
        }

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedMCPToolOutput": json.dumps(output),
        }
    }))


if __name__ == "__main__":
    main()
