"""MCP Server for bill management.

Thin transport layer - all logic lives in SDK.

WORKFLOW OVERVIEW:
This server provides tools for a phased bill-checking workflow:

Phase 1 (Autonomous): Call list tools to load state, then query external
sources (Monarch, email) to determine payment status for each bill.

Phase 2 (Summary): Present findings to user - overdue, due soon, and
items needing clarification.

Phase 3 (Resolution): Update config with user-provided info, re-verify.

Tools are organized by purpose:
- List tools: Start here to load current state
- Register tools: Add new bills/accounts discovered during review
- Update tools: Modify existing entries with discovered info
- Budget tools: Configure which bills count toward cash flow
- Config tools: Verify setup and show paths
"""

from typing import Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..sdk.common import accounts, budget, filters, properties
from ..sdk.common.config import get_config_path, load_config

mcp = FastMCP("bills")


# =============================================================================
# Credit Account Tools
# =============================================================================


@mcp.tool(
    name="list_credit_accounts",
    description="""List all credit accounts from config.

START HERE for Phase 1. Returns all tracked credit accounts including:
- Bank cards (Chase, Citi, etc.)
- Vendor/store financing (Best Buy, CareCredit, Home Depot)
- Any account with promo financing details

For each account you receive:
- name, last4, issuer: identification
- due_day: day of month payment due (null if unknown - flag for user)
- payment_method: auto_pay_full, auto_pay_min, or manual
- funding_account: which checking account pays this
- vendor: true for store/vendor financing (typically promo-based)
- promos: array of promo financing plans (see add_promo for details)
- notes: account-specific context (PDF mappings, quirks, etc.)

NEXT STEPS after calling this:
1. For each account, query Monarch for recent transactions to find last payment
2. Calculate next due date from due_day + last payment date
3. Flag accounts with due_day=null or funding_account=null for user input
4. For accounts with promos, verify payment plan clears each promo before expiration
5. Use update_credit_account to save discovered info (balances, due dates)

See also: list_promo_accounts (filtered view of accounts with active promos)""",
)
async def list_credit_accounts_tool() -> dict:
    accts = accounts.list_credit_accounts()
    return {"credit_accounts": [a.model_dump() for a in accts], "count": len(accts)}


@mcp.tool(
    name="get_credit_account",
    description="""Get a single credit account by last4 digits.

Use when you need details for a specific account during processing.
Returns same fields as list_credit_accounts but for one account.

If not found, returns found=false with error message.""",
)
async def get_credit_account_tool(
    last4: str = Field(description="Last 4 digits of the account"),
) -> dict:
    acct = accounts.get_credit_account(last4)
    if acct:
        return {"credit_account": acct.model_dump(), "found": True}
    return {"credit_account": None, "found": False, "error": f"No account with last4={last4}"}


@mcp.tool(
    name="register_credit_account",
    description="""Add a new credit account to tracking.

Use during Phase 1 when you discover an account not yet in config:
- Found payment in Monarch to unknown creditor
- User mentions a card not being tracked
- Email shows statement for untracked account

Required: name, issuer
Optional but recommended: last4, due_day, payment_method, funding_account

For vendor/store financing (Best Buy, Home Depot, CareCredit, etc.):
- Set vendor=true
- Use add_promo after registration to add 0% financing plans

After registering, the account appears in list_credit_accounts output.""",
)
async def register_credit_account_tool(
    name: str = Field(description="Display name, e.g. 'Sapphire Preferred', 'Best Buy'"),
    issuer: str = Field(description="Card issuer/servicer, e.g. 'Chase', 'Synchrony'"),
    last4: Optional[str] = Field(default=None, description="Last 4 digits of account number"),
    due_day: Optional[int] = Field(default=None, description="Day of month due (1-31)"),
    payment_method: str = Field(default="manual", description="auto_pay_full, auto_pay_min, manual"),
    funding_account: Optional[str] = Field(default=None, description="Last4 of funding account that pays this"),
    vendor: bool = Field(default=False, description="True for vendor/store financing - typically promo-based"),
    notes: Optional[str] = Field(default=None, description="Account-specific notes, PDF mappings, quirks"),
) -> dict:
    success, result = accounts.register_credit_account(
        name=name,
        issuer=issuer,
        last4=last4,
        due_day=due_day,
        payment_method=payment_method,
        funding_account=funding_account,
        vendor=vendor,
        notes=notes,
    )
    if success:
        return {"success": True, "credit_account": result.model_dump()}
    return {"success": False, "error": result}


@mcp.tool(
    name="update_credit_account",
    description="""Update an existing credit account with discovered information.

Use during Phase 1 to save info discovered from Monarch/email:
- Due day discovered from statement email
- Payment method confirmed

Use during Phase 3 to save user-provided clarifications:
- Due day user confirmed
- Payment method user specified
- Funding account user identified

Only fields you provide are updated - others remain unchanged.

For promo financing, use add_promo/update_promo/remove_promo instead.""",
)
async def update_credit_account_tool(
    last4: str = Field(description="Last 4 digits to identify the account"),
    name: Optional[str] = Field(default=None, description="New display name"),
    issuer: Optional[str] = Field(default=None, description="New issuer"),
    due_day: Optional[int] = Field(default=None, description="Day of month due (1-31)"),
    payment_method: Optional[str] = Field(default=None, description="auto_pay_full, auto_pay_min, manual"),
    funding_account: Optional[str] = Field(default=None, description="Last4 of funding account"),
    vendor: Optional[bool] = Field(default=None, description="Update vendor flag"),
    notes: Optional[str] = Field(default=None, description="Account-specific notes, PDF mappings, quirks"),
) -> dict:
    success, result = accounts.update_credit_account(
        last4,
        name=name,
        issuer=issuer,
        due_day=due_day,
        payment_method=payment_method,
        funding_account=funding_account,
        vendor=vendor,
        notes=notes,
    )
    if success:
        return {"success": True, "credit_account": result.model_dump()}
    return {"success": False, "error": result}


@mcp.tool(
    name="list_promo_accounts",
    description="""List credit accounts with active 0% promo financing.

CRITICAL CHECK during Phase 1. Returns only accounts with promos array populated.

These are HIGH PRIORITY because:
- If promo expires with remaining balance, ALL deferred interest hits retroactively
- A $10k balance at 29.99% deferred = ~$3k interest bomb if deadline missed

For each promo in each account, verify:
1. expires is in the future (if past, ALERT USER IMMEDIATELY)
2. Payment plan will clear balance before deadline:
   - Calculate months until expires
   - Required monthly = balance / months_remaining
   - Compare to payment_amount - flag if insufficient
3. Check 'updated' field - stale balances (>30 days) should be refreshed

Flag in Phase 2 summary if:
- < 90 days until expiration = WARNING
- < 30 days until expiration = CRITICAL
- Payment math doesn't clear balance in time = URGENT

This is a filtered view of list_credit_accounts - accounts with at least one promo.""",
)
async def list_promo_accounts_tool() -> dict:
    accts = accounts.list_promo_accounts()
    return {"promo_accounts": [a.model_dump() for a in accts], "count": len(accts)}


# =============================================================================
# Promo Financing Tools
# =============================================================================


@mcp.tool(
    name="add_promo",
    description="""Add a promo financing plan to a credit account.

Use when you discover a new 0% promo on an existing account:
- Citi Flex Pay plan activated
- Best Buy 0% financing purchase
- Store card promotional balance

Required: account_last4, balance
Recommended: expires (CRITICAL deadline), payment_amount, updated

The 'updated' field tracks when balance was last verified - set to today's date.
Stale balances (>30 days old) should be flagged for refresh.

One account can have multiple promos (e.g., Citi often has 4+ Flex plans).""",
)
async def add_promo_tool(
    account_last4: str = Field(description="Last 4 of the credit account"),
    balance: float = Field(description="Current promo balance"),
    description: Optional[str] = Field(default=None, description="Plan ID or purchase description"),
    expires: Optional[str] = Field(default=None, description="Promo expiration YYYY-MM-DD - CRITICAL"),
    payment_amount: Optional[float] = Field(default=None, description="Scheduled payment for this promo"),
    payments_remaining: Optional[int] = Field(default=None, description="Payments left to clear balance"),
    monthly_fee: Optional[float] = Field(default=None, description="Monthly fee if any (Citi Flex)"),
    updated: Optional[str] = Field(default=None, description="When balance was verified YYYY-MM-DD"),
) -> dict:
    success, result = accounts.add_promo(
        account_last4=account_last4,
        balance=balance,
        description=description,
        expires=expires,
        payment_amount=payment_amount,
        payments_remaining=payments_remaining,
        monthly_fee=monthly_fee,
        updated=updated,
    )
    if success:
        return {"success": True, "promo": result.model_dump()}
    return {"success": False, "error": result}


@mcp.tool(
    name="update_promo",
    description="""Update an existing promo financing plan.

Use to update balance, payment info, or expiration for an existing promo.
promo_index is 0-based (first promo is 0, second is 1, etc.).

ALWAYS update the 'updated' field when changing balance to track freshness.
Only fields you provide are updated.""",
)
async def update_promo_tool(
    account_last4: str = Field(description="Last 4 of the credit account"),
    promo_index: int = Field(description="0-based index of promo in array"),
    description: Optional[str] = Field(default=None, description="Plan ID or purchase description"),
    balance: Optional[float] = Field(default=None, description="Updated promo balance"),
    expires: Optional[str] = Field(default=None, description="Promo expiration YYYY-MM-DD"),
    payment_amount: Optional[float] = Field(default=None, description="Scheduled payment amount"),
    payments_remaining: Optional[int] = Field(default=None, description="Payments left"),
    monthly_fee: Optional[float] = Field(default=None, description="Monthly fee if any"),
    updated: Optional[str] = Field(default=None, description="When balance was verified YYYY-MM-DD"),
) -> dict:
    success, result = accounts.update_promo(
        account_last4=account_last4,
        promo_index=promo_index,
        description=description,
        balance=balance,
        expires=expires,
        payment_amount=payment_amount,
        payments_remaining=payments_remaining,
        monthly_fee=monthly_fee,
        updated=updated,
    )
    if success:
        return {"success": True, "promo": result.model_dump()}
    return {"success": False, "error": result}


@mcp.tool(
    name="remove_promo",
    description="""Remove a promo financing plan from an account.

Use when a promo is fully paid off or the plan was cancelled.
promo_index is 0-based (first promo is 0, second is 1, etc.).

After removal, remaining promos shift down (index 2 becomes 1, etc.).""",
)
async def remove_promo_tool(
    account_last4: str = Field(description="Last 4 of the credit account"),
    promo_index: int = Field(description="0-based index of promo to remove"),
) -> dict:
    success, message = accounts.remove_promo(
        account_last4=account_last4,
        promo_index=promo_index,
    )
    return {"success": success, "message": message}


# =============================================================================
# Funding Account Tools
# =============================================================================


@mcp.tool(
    name="list_funding_accounts",
    description="""List checking/savings accounts used to pay bills.

Call early in Phase 1 to understand payment flow. Returns:
- name: display name (e.g. 'Chase Checking', 'Ally Savings')
- last4: identifier used in funding_account fields elsewhere
- bank: institution name
- monarch_id: Monarch account ID for balance/transaction queries

Use this to:
1. Map funding_account references in credit accounts and property bills
2. Get monarch_id for querying transactions in that account
3. Verify funding accounts have sufficient balance for upcoming bills

When processing a bill, look up its funding_account here to get the monarch_id,
then query Monarch transactions for that account to find payments.""",
)
async def list_funding_accounts_tool() -> dict:
    accts = accounts.list_funding_accounts()
    return {"funding_accounts": [a.model_dump() for a in accts], "count": len(accts)}


@mcp.tool(
    name="register_funding_account",
    description="""Add a new checking/savings account for paying bills.

Use when you discover payments coming from an account not in config.

Required: name, last4, bank
Optional: monarch_id (add later once you find the account in Monarch)

After registering, this last4 can be used as funding_account when
registering or updating credit accounts and property bills.""",
)
async def register_funding_account_tool(
    name: str = Field(description="Display name, e.g. 'Chase Checking'"),
    last4: str = Field(description="Last 4 digits of account number"),
    bank: str = Field(description="Bank name, e.g. 'Chase', 'Ally'"),
    monarch_id: Optional[str] = Field(default=None, description="Monarch account ID for queries"),
) -> dict:
    success, result = accounts.register_funding_account(
        name=name, last4=last4, bank=bank, monarch_id=monarch_id
    )
    if success:
        return {"success": True, "funding_account": result.model_dump()}
    return {"success": False, "error": result}


# =============================================================================
# Property Tools
# =============================================================================


@mcp.tool(
    name="list_properties",
    description="""List all properties and their associated bills.

Call during Phase 1 after credit accounts. Returns properties with:
- name: identifier (e.g. 'Primary Residence', 'Rental 1')
- type: residence, rental, personal
- address: full address if known
- bills: array of property bills (see list_property_bills for details)

Process each property's bills:
1. For each bill, query Monarch for recent payments to that vendor
2. Determine status: current, due soon, overdue, unknown
3. Flag bills with missing due_day or funding_account
4. Update bill info with discovered data

See also: list_property_bills for detailed bill info for one property.""",
)
async def list_properties_tool() -> dict:
    props = properties.list_properties()
    return {"properties": [p.model_dump() for p in props], "count": len(props)}


@mcp.tool(
    name="list_property_bills",
    description="""List all bills for a specific property.

Use when processing a single property's bills. Returns:
- name: bill type (Mortgage, Water, Trash, Electric, etc.)
- vendor: who gets paid (e.g. Mortgage Company, City Water Dept)
- due_day: day of month due (null = unknown, flag for user)
- amount: expected amount (null = varies or unknown)
- payment_method: auto_draft, auto_pay, manual
- funding_account: last4 of account that pays this
- managed_by: if set (e.g. 'spouse'), only check for problems, skip detailed tracking

For managed_by='spouse' bills:
- Still verify no overdue alerts or disconnection notices
- Don't collect detailed transaction history
- Don't flag for missing config - spouse handles it
- Only include in summary if actual problem detected""",
)
async def list_property_bills_tool(
    property_name: str = Field(description="Property name, e.g. 'Primary Residence', 'Rental 1'"),
) -> dict:
    prop, bills = properties.list_property_bills(property_name)
    if prop is None:
        return {"property": property_name, "bills": [], "count": 0, "error": f"Property '{property_name}' not found"}
    return {"property": prop.name, "bills": [b.model_dump() for b in bills], "count": len(bills)}


@mcp.tool(
    name="register_property_bill",
    description="""Add a new bill to a property.

Use when you discover a bill not yet tracked:
- Found payment in Monarch to utility not in config
- User mentions a bill for a property
- Email shows bill statement for untracked service

If the property doesn't exist, it will be created automatically.

Required: property_name, bill_name, vendor
Recommended: due_day, payment_method, funding_account

For non-property bills (T-Mobile, insurance), use property_name='Personal' with type='personal'.

Property types: residence, rental, personal

For bills managed by someone else (e.g., spouse), set managed_by.
These are still monitored for problems but not tracked in detail.

After registering, the bill appears in list_properties and list_property_bills output.""",
)
async def register_property_bill_tool(
    property_name: str = Field(description="Property name - created if doesn't exist"),
    bill_name: str = Field(description="Bill type: Mortgage, Water, Trash, Electric, HOA, etc."),
    vendor: str = Field(description="Vendor/payee name"),
    due_day: Optional[int] = Field(default=None, description="Day of month due (1-31)"),
    amount: Optional[float] = Field(default=None, description="Expected amount"),
    payment_method: str = Field(default="manual", description="auto_draft, auto_pay, manual"),
    funding_account: Optional[str] = Field(default=None, description="Last4 of funding account"),
    type: str = Field(default="residence", description="residence, rental, personal", alias="type"),
    managed_by: Optional[str] = Field(default=None, description="Who manages this bill (e.g., 'spouse')"),
    notes: Optional[str] = Field(default=None, description="Bill-specific notes"),
) -> dict:
    success, result = properties.register_property_bill(
        property_name=property_name,
        bill_name=bill_name,
        vendor=vendor,
        due_day=due_day,
        amount=amount,
        payment_method=payment_method,
        funding_account=funding_account,
        type=type,
        managed_by=managed_by,
        notes=notes,
    )
    if success:
        return {"success": True, "property": property_name, "bill": result.model_dump()}
    return {"success": False, "error": result}


@mcp.tool(
    name="update_property",
    description="""Update property metadata (address, type, tax_id, notes).

Use to add or update property information. Only fields you provide are updated.""",
)
async def update_property_tool(
    name: str = Field(description="Property name to update"),
    address: Optional[str] = Field(default=None, description="Full address"),
    type: Optional[str] = Field(default=None, description="residence, rental, personal"),
    tax_id: Optional[str] = Field(default=None, description="Property tax ID or parcel number"),
    notes: Optional[str] = Field(default=None, description="Property-specific notes"),
) -> dict:
    success, result = properties.update_property(
        name,
        address=address,
        type=type,
        tax_id=tax_id,
        notes=notes,
    )
    if success:
        return {"success": True, "property": result.model_dump()}
    return {"success": False, "error": result}


# =============================================================================
# Budget Scope Tools
# =============================================================================


@mcp.tool(
    name="get_budget_scope",
    description="""Get budget scope settings - which bills count toward cash flow calculations.

This configuration determines what's included when calculating:
- Available cash for upcoming bills
- Monthly budget requirements
- Cash flow projections

Settings:
- properties_residence: include primary residence bills (default true)
- properties_rental: include rental property bills (default false - separate business)
- credit: include credit account payments (default true)
- subscriptions: include subscription expenses (default true)

This does NOT affect bill monitoring - all configured bills are checked for
delinquency regardless of budget scope. Budget scope only affects cash flow math.

See also: update_budget_scope to change these settings.""",
)
async def get_budget_scope_tool() -> dict:
    return budget.get_budget_scope().model_dump()


@mcp.tool(
    name="update_budget_scope",
    description="""Update budget scope settings.

Use to change which bills count toward cash flow calculations.
Only fields you provide are updated.

Common configurations:
- Track only personal bills: properties_residence=true, properties_rental=false
- Include everything: all fields true
- Credit only: credit=true, others false

Changes take effect immediately for subsequent budget calculations.

Note: This does NOT affect monitoring. Even if properties_rental=false,
rental property bills are still checked for delinquency.""",
)
async def update_budget_scope_tool(
    properties_residence: Optional[bool] = Field(default=None, description="Include primary residence bills"),
    properties_rental: Optional[bool] = Field(default=None, description="Include rental property bills"),
    credit: Optional[bool] = Field(default=None, description="Include credit accounts"),
    subscriptions: Optional[bool] = Field(default=None, description="Include subscriptions"),
) -> dict:
    result = budget.update_budget_scope(
        properties_residence=properties_residence,
        properties_rental=properties_rental,
        credit=credit,
        subscriptions=subscriptions,
    )
    return {"success": True, "budget_scope": result.model_dump()}


# =============================================================================
# Bill Filter Tools
# =============================================================================


@mcp.tool(
    name="get_bill_filters",
    description="""Get the category patterns used to filter Monarch's list_recurring.

Returns glob patterns that define which Monarch recurring categories are
"consequential bills" — obligations with consequences for non-payment
(credit damage, service disconnection, foreclosure, etc.).

Use these patterns to filter the output of Monarch's list_recurring tool.
Match each recurring stream's category against these patterns using
case-insensitive glob matching.

Example patterns: '*Mortgage*', 'Water', '*Utilities*', 'Credit Card Payment'""",
)
async def get_bill_filters_tool() -> dict:
    bill_filters = filters.get_bill_filters()
    return {"categories": bill_filters.categories, "count": len(bill_filters.categories)}


@mcp.tool(
    name="set_bill_filters",
    description="""Replace the entire bill filter category list.

Use when the user wants to redefine which Monarch categories count as
consequential bills. This replaces all existing patterns.""",
)
async def set_bill_filters_tool(
    categories: list[str] = Field(description="List of glob patterns, e.g. ['*Mortgage*', 'Water', '*Insurance*']"),
) -> dict:
    result = filters.set_bill_filters(categories)
    return {"success": True, "categories": result.categories, "count": len(result.categories)}


@mcp.tool(
    name="add_bill_filter",
    description="""Add a single category pattern to the bill filter list.

Use when a new Monarch category should be treated as a consequential bill.
No-op if the pattern already exists.""",
)
async def add_bill_filter_tool(
    pattern: str = Field(description="Glob pattern to add, e.g. '*Mortgage*' or 'Phone'"),
) -> dict:
    result = filters.add_bill_filter(pattern)
    return {"success": True, "categories": result.categories, "count": len(result.categories)}


@mcp.tool(
    name="remove_bill_filter",
    description="""Remove a category pattern from the bill filter list.

Use when a Monarch category should no longer be treated as a consequential bill.""",
)
async def remove_bill_filter_tool(
    pattern: str = Field(description="Exact pattern to remove"),
) -> dict:
    success, message = filters.remove_bill_filter(pattern)
    return {"success": success, "message": message}


# =============================================================================
# Config Tools
# =============================================================================


@mcp.tool(
    name="validate_config",
    description="""Validate config file and return summary.

Call at start of Phase 1 to verify setup. Returns:
- valid: true/false
- config_path: where config lives
- summary: counts of credit_accounts, accounts_with_promo, properties, funding_accounts

If config doesn't exist or is invalid, returns valid=false with error details.

Use show_config_path if you need to tell user where to manually edit config.""",
)
async def validate_config_tool() -> dict:
    config_path = get_config_path()
    if not config_path.exists():
        return {
            "valid": False,
            "error": f"Config file not found at {config_path}",
            "hint": "Use register_* tools to create config entries - file is created automatically",
        }
    try:
        config = load_config()
        accounts_with_promo = sum(1 for a in config.credit_accounts if len(a.promos) > 0)
        total_promos = sum(len(a.promos) for a in config.credit_accounts)
        return {
            "valid": True,
            "config_path": str(config_path),
            "summary": {
                "credit_accounts": len(config.credit_accounts),
                "accounts_with_promo": accounts_with_promo,
                "total_promo_plans": total_promos,
                "properties": len(config.properties),
                "funding_accounts": len(config.funding_accounts),
                "bill_filter_patterns": len(config.bill_filters.categories),
            },
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


@mcp.tool(
    name="show_config_path",
    description="""Show the config file path for manual editing.

Returns the XDG-compliant path where config lives:
- Typically ~/.config/bills/config.yaml
- Created automatically when you first use register_* tools

Use this to tell user where to find config for manual edits or backup.""",
)
async def show_config_path_tool() -> dict:
    config_path = get_config_path()
    return {"config_path": str(config_path), "exists": config_path.exists()}


# =============================================================================
# Server Entry Point
# =============================================================================


def run_server():
    """Run the MCP server with stdio transport."""
    mcp.run()


if __name__ == "__main__":
    run_server()
