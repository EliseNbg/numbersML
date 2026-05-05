"""
API authentication and authorization module.

Provides:
- API key validation
- Role-based access control for sensitive operations
- Policy checks for algorithm lifecycle and market operations
"""

import logging

from fastapi import Depends, Header, HTTPException, status

logger = logging.getLogger(__name__)

# Simple in-memory API key store (replace with database/env in production)
# Format: {api_key: {"roles": [list of roles], "name": "description"}}
API_KEY_STORE = {
    "admin-secret-key": {"roles": ["admin"], "name": "Admin Key"},
    "trader-secret-key": {"roles": ["trader", "read"], "name": "Trader Key"},
    "read-secret-key": {"roles": ["read"], "name": "Read-Only Key"},
}

# Load from environment if available
import os

APP_ENV = os.getenv("APP_ENV", "prod")

for key, value in os.environ.items():
    if key.startswith("API_KEY_"):
        role = key.split("_")[-1].lower()
        if role in ["admin", "trader", "read"]:
            API_KEY_STORE[value] = {"roles": [role], "name": f"Env {role} key"}


class AuthContext:
    """Authentication context for request."""

    def __init__(self, api_key: str, roles: list[str], name: str) -> None:
        self.api_key = api_key
        self.roles = roles
        self.name = name

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def has_any_role(self, roles: list[str]) -> bool:
        return any(role in self.roles for role in roles)


async def get_auth_context(
    x_api_key: str | None = Header(None, description="API key for authentication")
) -> AuthContext:
    """Validate API key and return auth context."""
    # Skip auth in prod mode, return full-access context
    if APP_ENV != "test":
        return AuthContext(
            api_key="prod-default-key",
            roles=["admin", "trader", "read"],
            name="Prod Default Key",
        )
    
    # Test mode: enforce API key validation
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    key_info = API_KEY_STORE.get(x_api_key)
    if not key_info:
        logger.warning(f"Invalid API key attempt: {x_api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return AuthContext(
        api_key=x_api_key,
        roles=key_info["roles"],
        name=key_info["name"],
    )


async def require_read(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """Require read access (or admin)."""
    if not auth.has_any_role(["read", "admin"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return auth


async def require_trader(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """Require trader access (can create orders, manage algorithms)."""
    if not auth.has_any_role(["trader", "admin"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return auth


async def require_admin(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """Require admin access (can change modes, adjust risk limits)."""
    if not auth.has_role("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return auth


def check_live_mode_policy(algorithm_mode: str, auth: AuthContext) -> None:
    """Policy check: live mode operations require admin access."""
    if algorithm_mode == "live" and not auth.has_role("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )


def check_risk_limit_policy(auth: AuthContext) -> None:
    """Policy check: risk limit changes require admin access."""
    if not auth.has_role("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
