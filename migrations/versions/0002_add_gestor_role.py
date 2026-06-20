"""Add GESTOR role — family head distinct from platform ADMIN

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-16

Three-tier hierarchy:
  ADMIN   — Orbita platform operator (manages market data, instruments)
  GESTOR  — Family head: created via registration, manages family members,
             has access to all user-facing pages including investments
  MEMBER  — Family member added by GESTOR

Migration steps:
  1. Add 'GESTOR' value to the userrole PostgreSQL enum.
  2. Convert all existing ADMIN users to GESTOR (they were family heads).
     Platform admins will be re-seeded separately.
"""
from alembic import op

# revision identifiers
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add 'GESTOR' value to the PostgreSQL enum.
    # Existing ADMIN users (platform operators) keep their ADMIN role.
    # Going forward, registration creates GESTOR users; ADMIN is reserved
    # for the Orbita platform operator only.
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'GESTOR'")


def downgrade() -> None:
    # Revert GESTOR users to MEMBER before removing the value.
    # (PostgreSQL does not support DROP VALUE without recreating the type.)
    op.execute("UPDATE users SET role = 'MEMBER' WHERE role = 'GESTOR'")
