"""The three crypto parts bundled for the graph and the API."""

from dataclasses import dataclass, field

from app.crypto.audit import AuditLog, AuditStore
from app.crypto.keys import KeyRing, Purpose
from app.crypto.tokens import Pseudonymizer, TokenRegistry
from app.crypto.vault import Vault, VaultStore


@dataclass
class CryptoServices:
    pseudonymizer: Pseudonymizer
    vault: Vault
    audit: AuditLog
    actor: str = field(default="system")

    @classmethod
    def build(
        cls,
        ring: KeyRing,
        audit_store: AuditStore | None = None,
        vault_store: VaultStore | None = None,
        registry: TokenRegistry | None = None,
        actor: str = "system",
    ) -> "CryptoServices":
        audit = AuditLog(ring[Purpose.AUDIT], audit_store)
        return cls(
            Pseudonymizer(ring[Purpose.TOKEN], registry),
            Vault(ring[Purpose.VAULT], audit, vault_store),
            audit,
            actor,
        )
