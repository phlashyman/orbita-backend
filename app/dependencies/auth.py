"""
Authentication dependencies for Orbita.

Provides:
- Password hashing and verification via PassLib (bcrypt)
- JWT token creation and decoding via python-jose
- FastAPI dependencies for extracting and validating the current user
- Role-based access control (RBAC) guards
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a plain password with bcrypt."""
    return pwd_context.hash(password)


# ---------------------------------------------------------------------------
# JWT handling
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

ALGORITHM = "HS256"


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token with the provided payload.

    Args:
        data: Dictionary to encode in the JWT (must include ``sub``).
        expires_delta: Optional custom expiry duration. Defaults to
            ``settings.access_token_expire_minutes``.

    Returns:
        The encoded JWT string.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token.

    Args:
        token: The JWT string from the Authorization header.

    Returns:
        The decoded token payload as a dictionary.

    Raises:
        HTTPException: 401 if the token is expired or invalid.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract the JWT from the Authorization header, decode it, and return
    the corresponding ``User`` database row.

    Raises:
        HTTPException: 401 if the token is missing, invalid, or the user
            does not exist / is soft-deleted.
    """
    payload = decode_access_token(token)
    user_id: Optional[str] = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency wrapper that simply passes through the current user.

    In the future this can be extended to check for soft-deletion or
    account-suspension flags beyond the ``deleted_at`` guard in
    ``get_current_user``.

    Raises:
        HTTPException: 401 if the user is inactive.
    """
    if current_user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Ensure the authenticated user is the platform ``ADMIN`` (Orbita operator).

    Raises:
        HTTPException: 403 if the user's role is not ``ADMIN``.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin privileges required",
        )
    return current_user


async def require_gestor(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """Ensure the authenticated user is a ``GESTOR`` (Gestor da Família).

    Platform ADMINs are also granted access so they can assist any family.

    Raises:
        HTTPException: 403 if the user is a plain MEMBER.
    """
    if current_user.role not in (UserRole.GESTOR, UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gestor da Família privileges required",
        )
    return current_user
