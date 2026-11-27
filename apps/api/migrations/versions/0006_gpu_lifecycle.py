"""Persist the state of the managed GPU for this environment."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gpu_lifecycle",
        sa.Column("worker_id", sa.Text(), primary_key=True),
        sa.Column("phase", sa.Text(), nullable=False),
        sa.Column("hostname", sa.Text()),
        sa.Column("instance_id", sa.Uuid()),
        sa.Column("volume_id", sa.Uuid()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("idle_since", sa.DateTime(timezone=True)),
        sa.Column("retry_at", sa.DateTime(timezone=True)),
        sa.Column("window_started_at", sa.DateTime(timezone=True)),
        sa.Column("launches", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("gpu_lifecycle")
