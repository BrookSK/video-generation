"""consentimento do avatar criado pela API

Acrescenta em avatars o nome de quem autorizou o uso da imagem (consent_name) e a chave de
API que criou o avatar (created_by_api_key_id). Aditiva: avatares do painel ficam com as
duas colunas nulas e seguem com authorized_by_user_id.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-13 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_API_KEY_FK = "fk_avatars_created_by_api_key_id_api_keys"


def upgrade() -> None:
    op.add_column("avatars", sa.Column("consent_name", sa.Text(), nullable=True))
    op.add_column("avatars", sa.Column("created_by_api_key_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f(_API_KEY_FK),
        "avatars",
        "api_keys",
        ["created_by_api_key_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(op.f(_API_KEY_FK), "avatars", type_="foreignkey")
    op.drop_column("avatars", "created_by_api_key_id")
    op.drop_column("avatars", "consent_name")
