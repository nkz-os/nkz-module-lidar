"""
Authentication middleware for LIDAR module.

Trusts api-gateway injected headers. Does NOT validate JWKS/JWT directly.
The api-gateway has already validated the token against Keycloak and injects
X-Tenant-ID, X-User-ID, X-User-Roles headers.
"""

import logging
from typing import Optional, List
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

security = HTTPBearer()


def get_tenant_id(request: Request) -> str:
    """Extract tenant ID from request headers (injected by api-gateway)."""
    tenant_id = request.headers.get('X-Tenant-ID')
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required"
        )
    return tenant_id


def get_user_id(request: Request) -> Optional[str]:
    """Extract user ID from request headers (injected by api-gateway)."""
    return request.headers.get('X-User-ID')


def get_user_roles(request: Request) -> List[str]:
    """Extract user roles from request headers (injected by api-gateway)."""
    roles_header = request.headers.get('X-User-Roles', '')
    return [r.strip() for r in roles_header.split(',') if r.strip()]


async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> dict:
    """
    Require authentication via api-gateway headers.

    The api-gateway validates the JWT and injects headers. This dependency
    reads those headers. If no token is present in the Authorization header
    (Bearer), the api-gateway may still inject tenant headers for
    cookie-authenticated requests.

    Returns dict with tenant_id, user_id, roles for downstream use.
    """
    tenant_id = request.headers.get('X-Tenant-ID')
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required — no tenant context",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "tenant_id": tenant_id,
        "user_id": request.headers.get('X-User-ID'),
        "roles": [r.strip() for r in request.headers.get('X-User-Roles', '').split(',') if r.strip()],
    }
