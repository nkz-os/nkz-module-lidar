"""
Authentication middleware for FastAPI.
"""

import logging
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt import PyJWKClient
import os

logger = logging.getLogger(__name__)

# JWT configuration
JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'RS256')
JWT_ISSUER = os.getenv('JWT_ISSUER', '')
JWKS_URL = os.getenv('JWKS_URL', f'{JWT_ISSUER}/protocol/openid-connect/certs')

# Cache for JWKS
_jwks_client: Optional[PyJWKClient] = None

security = HTTPBearer()


def get_jwks_client() -> PyJWKClient:
    """Get or create JWKS client."""
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(JWKS_URL)
    return _jwks_client


async def verify_token(token: str) -> dict:
    """Verify JWT token and return payload."""
    try:
        jwks_client = get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"verify_exp": True, "verify_iss": True}
        )
        
        return payload
        
    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error verifying token: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}"
        )


def get_tenant_id(request: Request) -> str:
    """Extract tenant ID from request headers."""
    tenant_id = request.headers.get('X-Tenant-ID')
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required"
        )
    return tenant_id


async def require_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> dict:
    """Dependency to require authentication.
    Reads token from Authorization header or httpOnly cookie (fallback).
    """
    token = None
    if credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get('nkz_token')

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = await verify_token(token)
    return payload


