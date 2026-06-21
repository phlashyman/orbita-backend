"""
Authentication router for Orbita.

Provides endpoints for:
- User registration (creates a new family + Gestor da Família user)
- Login via OAuth2 Password Flow
- Current user profile retrieval
- Family member management (Gestor only)
"""
from datetime import timedelta
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies.auth import (
    create_access_token,
    get_current_active_user,
    get_password_hash,
    require_admin,
    require_gestor,
    verify_password,
)
from app.models.family import Family
from app.models.user import User, UserRole

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UserRead(BaseModel):
    """Public user representation returned by API endpoints."""

    id: str
    name: str
    email: EmailStr
    role: UserRole
    family_id: str

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """OAuth2 token payload returned on successful login or registration."""

    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    """Payload for registering a new family and its first admin user."""

    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)
    family_name: str = Field(..., min_length=1, max_length=100)


class RegisterResponse(TokenResponse):
    """Registration response includes the token **and** the created user."""

    user: UserRead


class BootstrapAdminRequest(BaseModel):
    """Payload for creating the first platform admin. Only works when users table is empty."""

    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8)
    family_name: str = Field("Orbita Admin", min_length=1, max_length=100)


class LoginResponse(TokenResponse):
    """Login response includes the token **and** the authenticated user."""

    user: UserRead


class AddMemberRequest(BaseModel):
    """Payload for adding a new member to the Gestor's family."""

    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: UserRole = UserRole.MEMBER

    @field_validator("role")
    @classmethod
    def role_must_be_member(cls, v: UserRole) -> UserRole:
        """Only MEMBER can be added this way. GESTOR and ADMIN are created via other flows."""
        if v in (UserRole.ADMIN, UserRole.GESTOR):
            raise ValueError("Only MEMBER role can be assigned via member creation")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_to_read(user: User) -> UserRead:
    """Convert a SQLAlchemy ``User`` instance to the public ``UserRead`` schema."""
    return UserRead(
        id=str(user.id),
        name=user.name,
        email=user.email,
        role=user.role,
        family_id=str(user.family_id),
    )


async def _authenticate_user(
    db: AsyncSession, email: str, password: str
) -> User | None:
    """Fetch a user by email and verify the supplied password.

    Returns:
        The ``User`` instance if credentials are valid, otherwise ``None``.
    """
    result = await db.execute(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new family and create its first Gestor da Família.

    This is a single atomic database transaction — if either the family
    or the user insertion fails, everything is rolled back.
    """
    # Check for duplicate email
    existing = await db.execute(
        select(User).where(User.email == body.email)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create family and Gestor atomically
    family = Family(name=body.family_name)
    db.add(family)
    await db.flush()  # flush so family.id is populated

    user = User(
        family_id=family.id,
        name=body.name,
        email=body.email,
        hashed_password=get_password_hash(body.password),
        role=UserRole.GESTOR,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    # db.commit() is handled by get_db() upon successful return

    access_token = create_access_token(data={"sub": str(user.id)})

    return RegisterResponse(
        access_token=access_token,
        token_type="bearer",
        user=_user_to_read(user),
    )


@router.post(
    "/bootstrap-admin",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bootstrap_admin(
    body: BootstrapAdminRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create the FIRST platform admin. **Only works when the users table is empty.**

    Once a single user exists, this endpoint returns 403 Forbidden.
    Use this ONCE after database creation, then never again.
    """
    import logging
    from sqlalchemy import func

    # Count existing users
    result = await db.execute(select(func.count(User.id)))
    user_count = result.scalar()
    if user_count and user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Bootstrap disabled: {user_count} user(s) already exist. Register normally or use an existing admin account.",
        )

    # Check for duplicate email (belt-and-suspenders)
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    # Create family
    family = Family(name=body.family_name)
    db.add(family)
    await db.flush()

    # Create ADMIN user
    user = User(
        family_id=family.id,
        name=body.name,
        email=body.email,
        hashed_password=get_password_hash(body.password),
        role=UserRole.ADMIN,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id)})

    logging.getLogger("orbita").info(f"Bootstrap admin created: {user.email} (user_id={user.id}, family_id={family.id})")

    return RegisterResponse(
        access_token=access_token,
        token_type="bearer",
        user=_user_to_read(user),
    )


@router.post(
    "/login",
    response_model=LoginResponse,
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a user and return a JWT access token.

    Accepts ``username`` (email) and ``password`` via OAuth2 form data.
    """
    user = await _authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id)})

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=_user_to_read(user),
    )


@router.get("/me", response_model=UserRead)
async def read_current_user(
    current_user: User = Depends(get_current_active_user),
):
    """Return the currently authenticated user's profile."""
    return _user_to_read(current_user)


@router.post(
    "/family/members",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_family_member(
    body: AddMemberRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_gestor),
):
    """Add a new member to the Gestor's family.

    Requires the authenticated user to have the ``GESTOR`` role (or ADMIN).
    """
    # Check for duplicate email
    existing = await db.execute(
        select(User).where(User.email == body.email)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        family_id=admin.family_id,
        name=body.name,
        email=body.email,
        hashed_password=get_password_hash(body.password),
        role=body.role,
    )
    db.add(user)
    # db.commit() handled by get_db()

    return _user_to_read(user)


@router.get("/family/members", response_model=List[UserRead])
async def list_family_members(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_gestor),
):
    """List all non-deleted users belonging to the Gestor's family.

    Requires the ``GESTOR`` role (or platform ADMIN).
    """
    result = await db.execute(
        select(User).where(
            User.family_id == admin.family_id,
            User.deleted_at.is_(None),
        )
    )
    users = result.scalars().all()
    return [_user_to_read(u) for u in users]


@router.delete("/family/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_family_member(
    member_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_gestor),
):
    """Soft-delete a family member.

    Gestor cannot remove themselves. Requires GESTOR role (or platform ADMIN).
    """
    from uuid import UUID as _UUID
    try:
        member_uuid = _UUID(member_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid member id")

    if member_uuid == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove yourself")

    result = await db.execute(
        select(User).where(
            User.id == member_uuid,
            User.family_id == admin.family_id,
            User.deleted_at.is_(None),
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    from datetime import datetime
    member.deleted_at = datetime.utcnow()
    await db.commit()


@router.get("/users", response_model=List[UserRead])
async def list_all_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """List all non-deleted users on the platform. ADMIN only."""
    result = await db.execute(
        select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return [_user_to_read(u) for u in users]


@router.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Soft-delete any user. ADMIN only. Cannot delete yourself."""
    if str(current_user.id) == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account.")
    result = await db.execute(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.soft_delete()
    await db.commit()
