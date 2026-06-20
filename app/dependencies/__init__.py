"""
FastAPI dependencies shared across the Orbita backend.
"""
from app.dependencies.auth import (
    pwd_context,
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token,
    oauth2_scheme,
    get_current_user,
    get_current_active_user,
    require_admin,
)

__all__ = [
    "pwd_context",
    "verify_password",
    "get_password_hash",
    "create_access_token",
    "decode_access_token",
    "oauth2_scheme",
    "get_current_user",
    "get_current_active_user",
    "require_admin",
]
