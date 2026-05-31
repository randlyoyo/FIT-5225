"""
Authentication and authorisation for Cloud Run endpoints.

Two paths:
  1. User JWT (Cognito) — for /v1/query/by-file
  2. Shared secret     — for /internal/infer  (Lambda -> Cloud Run)
"""
import logging
from typing import Optional

import requests
from jose import jwt, JWTError
from jose.jwk import get_key
from fastapi import Request, HTTPException, status

from config import COGNITO_JWKS_URL, COGNITO_REGION, COGNITO_USER_POOL_ID
from config import INTERNAL_API_SECRET, INTERNAL_SECRET_HEADER

logger = logging.getLogger(__name__)

# Cached JWKS keys list — refreshed on key rotation
_jwks_keys: Optional[list] = None


def _fetch_jwks() -> list:
    """Fetch Cognito JWKS, with caching."""
    global _jwks_keys
    if _jwks_keys is not None:
        return _jwks_keys

    logger.info("Fetching Cognito JWKS from %s", COGNITO_JWKS_URL)
    resp = requests.get(COGNITO_JWKS_URL, timeout=10)
    resp.raise_for_status()
    _jwks_keys = resp.json()["keys"]
    return _jwks_keys


def verify_cognito_jwt(token: str) -> dict:
    """
    Verify a Cognito-issued ID token.
    Returns decoded claims on success, raises HTTPException on failure.
    """
    global _jwks_keys

    keys = _fetch_jwks()

    try:
        # Decode without verification first to get kid
        unverified = jwt.get_unverified_header(token)
        kid = unverified.get("kid")
        if not kid:
            raise HTTPException(status_code=401, detail="Missing kid in JWT header")

        # Find key by kid in JWKS
        key = get_key(kid, keys)
        if not key:
            # Refresh JWKS and retry once
            _jwks_keys = None
            keys = _fetch_jwks()
            key = get_key(kid, keys)
            if not key:
                raise HTTPException(status_code=401, detail="Unknown kid in JWT")

        # Verify token
        issuer = (
            f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/"
            f"{COGNITO_USER_POOL_ID}"
        )
        claims = jwt.decode(
            token,
            key.to_pem(),
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_exp": True, "verify_aud": False},
        )
        return claims

    except JWTError as e:
        logger.warning("JWT verification failed: %s", e)
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except requests.RequestException as e:
        logger.error("Failed to fetch JWKS: %s", e)
        raise HTTPException(
            status_code=500, detail="Auth service temporarily unavailable"
        )


def verify_internal_secret(request: Request) -> None:
    """Verify shared secret for internal Lambda -> Cloud Run calls."""
    provided = request.headers.get(INTERNAL_SECRET_HEADER, "")
    if not provided or provided != INTERNAL_API_SECRET:
        raise HTTPException(
            status_code=403, detail="Forbidden: invalid internal secret"
        )


def get_user_jwt(request: Request) -> str:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or malformed Authorization header"
        )
    return auth.removeprefix("Bearer ")
