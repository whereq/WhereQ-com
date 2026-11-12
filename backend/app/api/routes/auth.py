"""Auth routes.

Sign-in / sign-up / sign-out are handled entirely by Keycloak
(a Keycloak realm) via the SPA's redirect flow — the backend no longer issues
its own tokens. The only endpoint here returns the current user's profile,
provisioning the local ``users`` row from the Keycloak token on first call.
"""

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.user import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user, creating the local record if needed."""
    return current_user
