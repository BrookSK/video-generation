"""nome de exibição

Acrescenta users.display_name, texto anulável usado pela tela de pessoas do painel.
Usuários criados pela CLI ficam sem nome e a tela mostra o username.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26 23:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "display_name")
