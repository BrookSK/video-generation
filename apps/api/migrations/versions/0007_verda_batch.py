"""Record the active Verda Batch Job for an environment."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verda_batch_dispatches",
        sa.Column("worker_id", sa.Text(), primary_key=True),
        sa.Column("dispatch_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("launches", sa.Integer(), nullable=False),
        sa.Column("phase", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("verda_batch_dispatches")
