"""Admin use cases (API 4.13 to 4.19). The router checks the admin role; reveal checks it
again in the domain (Vault.reidentify), so a mistake in routing cannot leak a value."""

from typing import Any

from app.crypto.vault import AccessDeniedError, VaultError
from app.detectors.types import PiiType
from app.output.labels import EVENT_LABEL, FAMILY
from app.policy.actions import Action, actions_for_type
from app.services import clock
from app.services.container import Container
from app.services.errors import AppError
from app.storage.repos import RuleRepo, UserRepo
from app.storage.rows import UserRow
from app.storage.stores import SqlAuditStore, SqlBeliefStore

REVEALS_PER_HOUR = (10, 3600.0)


def actor_of(user: UserRow) -> str:
    return f"user:{user.id}"


class AdminService:
    def __init__(self, c: Container, user: UserRow) -> None:
        self.c, self.user = c, user
        self.rules = RuleRepo(c.db)

    def get_rules(self) -> dict[str, Any]:
        fixed = self.rules.all()
        return {
            "rules": [
                {
                    "pii_type": t.value,
                    "family": FAMILY[t],
                    "action": fixed[t][0].value if t in fixed else None,
                    "allowed_actions": [a.value for a in actions_for_type(t)],
                    "updated_at": fixed[t][1] if t in fixed else None,
                }  # fmt: skip
                for t in PiiType
            ]
        }

    def put_rules(self, rules: list[tuple[PiiType, Action | None]]) -> dict[str, Any]:
        seen: set[PiiType] = set()
        fixed: dict[PiiType, Action] = {}
        for t, a in rules:
            if t in seen:
                raise AppError("invalid_request", "Each type may appear once.", "rules")
            seen.add(t)
            if a is None:
                continue
            if a not in actions_for_type(t):
                raise AppError("action_not_allowed", field="rules")
            fixed[t] = a
        with self.c.db.transaction():
            self.rules.replace(fixed, self.user.id, clock.iso(clock.now()))
            self.c.crypto.audit.append(
                actor_of(self.user), "rules_changed",
                {"rules": {t.value: a.value for t, a in sorted(fixed.items())}},
            )  # fmt: skip
        return self.get_rules()

    def reveal(self, token: str, reason: str) -> dict[str, Any]:
        """Any logged-in user may call this; non-admins are refused AND logged (API 4.15)."""
        if self.user.role == "admin":
            self.c.limiter.hit(f"reveal:{self.user.id}", *REVEALS_PER_HOUR)
        vault = self.c.crypto_for(actor_of(self.user)).vault
        try:
            value = vault.reidentify(token, actor_of(self.user), self.user.role, reason)
        except AccessDeniedError as e:
            if self.user.role != "admin":
                raise AppError("forbidden") from e
            raise AppError("reason_too_short", field="reason") from e
        except VaultError as e:
            if "unknown token" in str(e):
                raise AppError("unknown_token", field="token") from e
            raise AppError("vault_integrity") from e
        entry = vault.store.get(token)
        last = self.c.crypto.audit.anchor()
        return {
            "token": token,
            "pii_type": entry.pii_type if entry else None,
            "value": value,
            "logged_as": last.seq if last else None,
        }

    def reset_beliefs(self) -> None:
        with self.c.db.transaction():
            n = SqlBeliefStore(self.c.db).reset()
            self.c.crypto.audit.append(actor_of(self.user), "beliefs_reset", {"count": n})

    def audit_page(self, before_seq: int | None, limit: int) -> dict[str, Any]:
        recs = SqlAuditStore(self.c.db).page(before_seq, limit + 1)
        more = len(recs) > limit
        recs = recs[:limit]
        ids = {int(r.actor.split(":", 1)[1]) for r in recs if r.actor.startswith("user:")}
        emails = UserRepo(self.c.db).emails(ids)
        items = []
        for r in recs:
            if r.actor.startswith("user:"):
                uid = int(r.actor.split(":", 1)[1])
                actor: dict[str, Any] = {"type": "user", "id": uid, "email": emails.get(uid)}
            else:
                actor = {"type": "system", "id": None, "email": None}
            items.append({
                "seq": r.seq, "ts": r.ts, "actor": actor, "event": r.event,
                "event_label": EVENT_LABEL.get(r.event, r.event), "details": r.payload,
            })  # fmt: skip
        return {"items": items, "next_before_seq": recs[-1].seq if more and recs else None}

    def verify(self) -> dict[str, Any]:
        saved = self.c.load_anchor()
        res = self.c.crypto.audit.verify(saved[0] if saved else None)
        return {
            "ok": res.ok, "checked": res.checked, "first_bad_seq": res.first_bad_seq,
            "reason": res.reason or None,
            "anchor": {"seq": saved[0].seq, "saved_at": saved[1]} if saved else None,
        }  # fmt: skip

    def save_anchor(self) -> dict[str, Any]:
        audit = self.c.crypto.audit
        nxt = audit.anchor()
        audit.append(actor_of(self.user), "anchor_saved", {"seq": (nxt.seq + 1) if nxt else 0})
        a = audit.anchor()
        assert a is not None
        saved_at = self.c.save_anchor(a)
        return {"seq": a.seq, "mac_prefix": a.mac[:16], "saved_at": saved_at}
