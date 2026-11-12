"""Authentication via an external Keycloak realm.

Authentication is delegated to the Keycloak realm hosted at
``settings.KEYCLOAK_URL``. The backend never issues its own session tokens;
it only *verifies* the RS256 access tokens minted by Keycloak and maps each
Keycloak identity (the ``sub`` claim) onto a local ``users`` row so that the
rest of the app — which references ``users.id`` via foreign keys — keeps
working unchanged.

FastAPI dependency hierarchy:
  get_current_user   →  verify Bearer token, provision/lookup local User
  get_optional_user  →  same, but returns None instead of raising
  get_principal      →  same, but returns the User *and* the raw claims, so a
                        route can make a role decision (staff) without decoding
                        the token twice
  require_staff      →  valid token that also carries a staff realm role

Public routes (no token): ``GET /api/health`` and the newsletter signup.

The legacy password helpers (``hash_password`` / ``verify_password``) are kept
only so existing utilities that reference them do not break; passwords are now
managed entirely by Keycloak.
"""

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db

if TYPE_CHECKING:  # pragma: no cover — typing only
    from app.models.user import User

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# ---------------------------------------------------------------------------
# JWKS cache — Keycloak signing keys, refreshed at most once per hour
# ---------------------------------------------------------------------------
_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 3600.0  # seconds


async def _get_jwks() -> dict:
    """Return cached Keycloak public keys, refreshing when stale."""
    global _jwks_cache, _jwks_fetched_at

    now = time.monotonic()
    if _jwks_cache and (now - _jwks_fetched_at) < _JWKS_TTL:
        return _jwks_cache

    url = (
        f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}"
        "/protocol/openid-connect/certs"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            _jwks_cache = resp.json()
            _jwks_fetched_at = now
            logger.info("Keycloak JWKS refreshed from %s", url)
    except Exception as exc:
        if _jwks_cache:
            logger.warning("JWKS refresh failed (using cached keys): %s", exc)
        else:
            logger.error("JWKS fetch failed and no cache available: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
            )
    return _jwks_cache  # type: ignore[return-value]


async def decode_keycloak_token(token: str) -> dict:
    """Verify the RS256 signature, issuer, expiry and authorized party.

    Returns the decoded claims dict. Raises HTTPException(401) on any problem.
    """
    expected_issuer = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}"
    try:
        jwks = await _get_jwks()
        payload: dict = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            issuer=expected_issuer,
            options={
                # Keycloak public-client tokens don't reliably carry the client
                # id in `aud`; we check `azp` below instead.
                "verify_aud": False,
                "verify_exp": True,
                "verify_iss": True,
            },
        )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as exc:
        logger.debug("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # `azp` (authorized party) ensures the token was issued for our SPA client,
    # not another app sharing the same Keycloak realm.
    azp = payload.get("azp")
    if azp != settings.KEYCLOAK_CLIENT_ID:
        logger.warning(
            "JWT azp mismatch: expected %r, got %r", settings.KEYCLOAK_CLIENT_ID, azp
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


# ---------------------------------------------------------------------------
# Map a Keycloak identity onto a local users row (provision on first use)
# ---------------------------------------------------------------------------
async def provision_user(db: AsyncSession, claims: dict):
    """Return the local User for these Keycloak claims, creating one if needed.

    Resolution order:
      1. by keycloak_id (the stable Keycloak ``sub``)
      2. by email — links a pre-existing local account to Keycloak (one-time)
      3. create a fresh local user
    """
    from app.models.user import User

    sub: str = claims["sub"]
    email: str = (claims.get("email") or f"{sub}@keycloak.local").lower()
    base_username: str = claims.get("preferred_username") or email.split("@")[0]

    # 1. existing Keycloak-linked user
    user = (
        await db.execute(select(User).where(User.keycloak_id == sub))
    ).scalar_one_or_none()
    if user:
        return user

    # 2. legacy local account with the same email → link it
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user:
        user.keycloak_id = sub
        await db.commit()
        await db.refresh(user)
        return user

    # 3. create a new local user, resolving username collisions
    username = base_username
    suffix = 0
    while (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none() is not None:
        suffix += 1
        username = f"{base_username}{suffix}"

    user = User(
        keycloak_id=sub,
        username=username,
        email=email,
        hashed_password=None,
        locale=(claims.get("locale") or "en")[:8],
        theme="dark",
        is_active=True,
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        # Concurrent first-request race — fall back to the row that won.
        await db.rollback()
        user = (
            await db.execute(select(User).where(User.keycloak_id == sub))
        ).scalar_one()
    return user


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------
_bearer = HTTPBearer(auto_error=False)


def has_staff_role(claims: dict) -> bool:
    """True when the token carries one of the configured staff realm roles.

    Realm roles are read from ``realm_access.roles`` — client roles
    (``resource_access``) deliberately do not count, so a role granted on one
    client cannot escalate on another.
    """
    roles = (claims.get("realm_access") or {}).get("roles") or []
    return bool(settings.staff_roles & set(roles))


@dataclass(frozen=True)
class Principal:
    """An authenticated caller: the local user *and* the raw Keycloak claims.

    The claims are carried because role checks (staff) need the realm roles,
    which are not stored on the local ``users`` row — decoding the token a
    second time per request would be wasteful.
    """

    user: "User"
    claims: dict

    @property
    def id(self) -> int:
        return self.user.id

    @property
    def is_staff(self) -> bool:
        return has_staff_role(self.claims)


async def _authenticate(
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
) -> tuple["User", dict]:
    """Verify the bearer token and provision/lookup the local user."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = await decode_keycloak_token(credentials.credentials)
    user = await provision_user(db, claims)
    return user, claims


async def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Principal:
    """Require a valid Keycloak Bearer token; return the principal.

    Use this instead of :func:`get_current_user` when the route also needs to
    make a role decision (staff) — it avoids decoding the token twice.
    """
    user, claims = await _authenticate(credentials, db)
    return Principal(user=user, claims=claims)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Require a valid Keycloak Bearer token; return the local User."""
    user, _ = await _authenticate(credentials, db)
    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Like get_current_user but returns None when no/invalid token is present."""
    if credentials is None:
        return None
    try:
        claims = await decode_keycloak_token(credentials.credentials)
        return await provision_user(db, claims)
    except HTTPException:
        return None


async def get_optional_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Principal | None:
    """Like get_principal but returns None when no/invalid token is present.

    Used by routes that are open to everyone but reveal more to their owner
    (e.g. a published route vs. a private one).
    """
    if credentials is None:
        return None
    try:
        user, claims = await _authenticate(credentials, db)
    except HTTPException:
        return None
    return Principal(user=user, claims=claims)


async def verify_token(token: str) -> dict | None:
    """Verify a raw token outside the request DI graph (used by WebSockets).

    Returns the decoded claims dict, or None if the token is invalid/expired.
    """
    try:
        return await decode_keycloak_token(token)
    except HTTPException:
        return None


async def require_staff(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Require a valid Keycloak token carrying a configured staff realm role.

    Used to gate staff-only surfaces (e.g. Maps API key management) and to let
    staff override ownership checks on user-authored content. The role is
    ``settings.STAFF_ROLE`` (default ``whereq-admin``) and must be assigned in
    the Keycloak realm.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = await decode_keycloak_token(credentials.credentials)
    if not has_staff_role(claims):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff role required",
        )
    return await provision_user(db, claims)
