"""
Pydantic schemas for User model — authentication and user management.
NEVER include hashed_password in any read schema.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict, EmailStr

from app.models.user import UserRole


class UserCreate(BaseModel):
    """Schema for creating a new user within a family."""

    name: str = Field(..., min_length=1, max_length=100, description="User's full name")
    email: EmailStr = Field(..., description="Unique email address")
    password: str = Field(
        ...,
        min_length=6,
        max_length=128,
        description="Plain-text password (hashed server-side)",
    )
    role: UserRole = Field(
        default=UserRole.MEMBER,
        description="User role: ADMIN (full access) or MEMBER (limited)",
    )


class UserRead(BaseModel):
    """Schema for reading a user — NEVER includes password."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique user identifier")
    family_id: uuid.UUID = Field(..., description="ID of the family this user belongs to")
    name: str = Field(..., description="User's full name")
    email: EmailStr = Field(..., description="User's email address")
    role: UserRole = Field(..., description="User role")
    created_at: datetime = Field(..., description="Timestamp when the user was created")


class UserLogin(BaseModel):
    """Schema for user login endpoint — email + password."""

    email: EmailStr = Field(..., description="Registered email address")
    password: str = Field(..., description="Account password")


class Token(BaseModel):
    """Schema for JWT token response after successful login."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type (always 'bearer')")


class TokenData(BaseModel):
    """Schema for decoded JWT token payload."""

    user_id: uuid.UUID | None = Field(
        default=None, description="UUID of the authenticated user"
    )
