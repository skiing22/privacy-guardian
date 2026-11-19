"""Users, passwords and server-side sessions (API 3.1, ADR-0022 D14).

Passwords: bcrypt over base64(SHA-256(password)). bcrypt only reads 72 bytes; pre-hashing
lets every byte of a 128-char password count, and base64 avoids NUL bytes.
Sessions: 32 random bytes in an HttpOnly cookie; the database stores only SHA-256 of it.
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass

import bcrypt

from app.crypto.audit import AuditLog
from app.services import clock
from app.services.errors import AppError
from app.services.ratelimit import RateLimiter
from app.storage.db import Database
from app.storage.repos import SessionRepo, UserRepo
from app.storage.rows import UserRow

__all__ = ["AuthService", "Session", "UserRow", "check_password", "hash_password"]

BCRYPT_ROUNDS = 12  # tests lower this
LOGIN_FAILS = (5, 300.0)  # per email + IP; reaching it locks for LOCKOUT_S
LOCKOUT_S = 60.0
LOGIN_IP = (30, 300.0)  # per IP
TOUCH_EVERY_S = 60


def _prehash(password: str) -> bytes:
    return base64.b64encode(hashlib.sha256(password.encode()).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(_prehash(password), hashed.encode())


_DUMMY: str | None = None


def _dummy_hash() -> str:
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password(secrets.token_hex(8))
    return _DUMMY


def session_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


@dataclass(frozen=True)
class Session:
    token: str
    user: UserRow
    max_age_s: int


class AuthService:
    def __init__(
        self, db: Database, audit: AuditLog, limiter: RateLimiter, idle_hours: int, max_days: int
    ) -> None:
        self.users, self.sessions = UserRepo(db), SessionRepo(db)
        self.audit, self.limiter = audit, limiter
        self.idle = clock.timedelta(hours=idle_hours)
        self.max = clock.timedelta(days=max_days)

    def create_user(self, email: str, password: str, role: str, actor: str = "system") -> int:
        if not 8 <= len(password) <= 128:
            raise AppError("invalid_request", "Password must be 8 to 128 characters.", "password")
        email = email.strip()
        if self.users.by_email(email) is not None:
            raise AppError("invalid_request", "That email already has an account.", "email")
        with self.users.db.transaction():
            uid = self.users.create(email, hash_password(password), role, clock.iso(clock.now()))
            self.audit.append(actor, "user_created", {"user_id": uid, "role": role})
        return uid

    def disable_user(self, email: str, actor: str = "system") -> None:
        u = self.users.by_email(email.strip())
        if u is None:
            raise AppError("not_found")
        with self.users.db.transaction():
            self.users.set_active(u.id, False)
            self.audit.append(actor, "user_disabled", {"user_id": u.id})

    def login(self, email: str, password: str, ip: str) -> Session:
        email = email.strip().lower()
        fail_key, ip_key = f"login:{email}|{ip}", f"login-ip:{ip}"
        lock_key = f"login-lock:{email}|{ip}"
        self.limiter.check(lock_key, 1, LOCKOUT_S)
        self.limiter.hit(ip_key, *LOGIN_IP)
        u = self.users.by_email(email)
        ok = check_password(password, u.password_hash if u else _dummy_hash())  # same timing
        if not (u and ok and u.is_active):
            self.limiter.add(fail_key)
            if self.limiter.retry_after(fail_key, *LOGIN_FAILS):
                self.limiter.clear(fail_key)
                self.limiter.add(lock_key)
            raise AppError("auth_failed")
        self.limiter.clear(fail_key)
        token = secrets.token_urlsafe(32)
        now = clock.now()
        self.sessions.create(session_hash(token), u.id, clock.iso(now), clock.iso(now + self.idle))
        return Session(token, u, int(self.idle.total_seconds()))

    def current(self, token: str | None) -> UserRow:
        if not token:
            raise AppError("auth_required")
        h = session_hash(token)
        row = self.sessions.get(h)
        if row is None:
            raise AppError("auth_required")
        created, last_seen, expires, user = row
        now = clock.now()
        if clock.parse(expires) <= now:
            self.sessions.delete(h)
            raise AppError("session_expired")
        if not user.is_active:
            raise AppError("auth_required")
        if (now - clock.parse(last_seen)).total_seconds() >= TOUCH_EVERY_S:
            new_exp = min(clock.parse(created) + self.max, now + self.idle)
            self.sessions.touch(h, clock.iso(now), clock.iso(new_exp))
        return user

    def logout(self, token: str | None) -> None:
        if token:
            self.sessions.delete(session_hash(token))
