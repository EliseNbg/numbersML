"""Domain model for API key management."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True)
class ApiKey:
    """API key domain model.

    Attributes:
        id: Unique identifier.
        name: Human-readable name for the key.
        environment: Target environment ('mainnet' or 'testnet').
        api_key_encrypted: Encrypted API key bytes.
        api_secret_encrypted: Encrypted API secret bytes.
        is_active: Whether the key is active.
        permissions: Key permissions (e.g., read, trade, withdraw).
        ip_whitelist: Optional IP whitelist.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
        last_used_at: Last usage timestamp.
        created_by: User who created the key.
    """

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    environment: str = "mainnet"
    api_key_encrypted: bytes = b""
    api_secret_encrypted: bytes = b""
    is_active: bool = True
    permissions: dict[str, bool] = field(default_factory=dict)
    ip_whitelist: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None
    created_by: str = "system"

    def to_public_dict(self) -> dict:
        """Return public representation (never includes secrets).

        Returns:
            Dict with all fields except encrypted secrets.
        """
        return {
            "id": str(self.id),
            "name": self.name,
            "environment": self.environment,
            "is_active": self.is_active,
            "permissions": self.permissions,
            "ip_whitelist": self.ip_whitelist,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_by": self.created_by,
        }
