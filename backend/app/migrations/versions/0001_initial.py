"""0001_initial: the 10 tables, checks, indexes and triggers of DATABASE.md.

Revision ID: 0001_initial
Revises:
"""

from alembic import op

from app.storage import schema_sql as s

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    for ddl in [*s.TABLES, *s.INDEXES, *s.TRIGGERS]:
        op.execute(ddl)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_no_update")
    op.execute("DROP TRIGGER IF EXISTS audit_no_delete")
    for name in s.TABLE_NAMES:
        op.execute(f"DROP TABLE IF EXISTS {name}")
