"""Indexes for login throttling (recent failed sign-ins by e-mail and by IP).

Revision ID: 0003
Revises: 0002
"""
from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_login_failed_email ON audit_logs (lower(actor_label), created_at) "
        "WHERE action = 'auth.login_failed'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_login_failed_ip ON audit_logs (ip_address, created_at) "
        "WHERE action = 'auth.login_failed'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_login_failed_ip")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_login_failed_email")
