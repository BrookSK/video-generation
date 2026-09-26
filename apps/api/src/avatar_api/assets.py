"""Avatares do painel: cadastro com tarefa de preparação, listagem, arquivamento e arquivos.

Arquivo de asset é imutável: não há edição; para trocar, a pessoa arquiva e cadastra outro.
"""

import uuid
from pathlib import Path
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from avatar_api.errors import ApiError
from avatar_api.models import AssetPrepareTask, Avatar, StoredFile
from avatar_api.storage import resolve_path, save_stream
from avatar_api.uploads import ValidatedImage

AvatarStatus = Literal["preparando", "ativo", "falha", "arquivado"]
AvatarFileKind = Literal["source", "prepared", "preview-9x16", "preview-16x9"]

_AVATAR_FILE_COLUMNS: dict[str, str] = {
    "source": "source_file_id",
    "prepared": "prepared_file_id",
    "preview-9x16": "preview_9x16_file_id",
    "preview-16x9": "preview_16x9_file_id",
}


def asset_dir(asset_id: uuid.UUID) -> str:
    return f"assets/{asset_id}"


def avatar_status(avatar: Avatar) -> AvatarStatus:
    return "arquivado" if avatar.archived_at is not None else avatar.prepare_status


def create_avatar(
    session: Session,
    data_dir: Path,
    user_id: uuid.UUID,
    name: str,
    voice: str,
    image: ValidatedImage,
) -> Avatar:
    """Grava a imagem, o avatar em preparando e a tarefa asset_prepare num único commit.

    Se qualquer passo falhar, nada fica: a transação é desfeita e o arquivo gravado é apagado.
    """
    avatar_id = uuid.uuid4()
    try:
        with image.path.open("rb") as stream:
            source = save_stream(
                session,
                data_dir,
                asset_dir(avatar_id),
                f"source{image.extension}",
                stream,
                image.sha256,
                image.content_type,
                commit=False,
            )
        avatar = Avatar(
            id=avatar_id,
            name=name,
            voice=voice,
            source_file_id=source.id,
            prepare_status="preparando",
            authorized_by_user_id=user_id,
            authorized_at=func.now(),
            created_by_user_id=user_id,
        )
        session.add(avatar)
        session.flush()
        session.add(AssetPrepareTask(avatar_id=avatar_id, status="queued"))
        session.commit()
    except BaseException:
        session.rollback()
        raise
    session.refresh(avatar)
    return avatar


def get_avatar(session: Session, avatar_id: uuid.UUID, for_update: bool = False) -> Avatar:
    avatar = session.get(Avatar, avatar_id, with_for_update=for_update)
    if avatar is None:
        raise ApiError(404, "NOT_FOUND", "Avatar não encontrado.")
    return avatar


def list_avatars(session: Session, include_archived: bool = False) -> list[Avatar]:
    query = select(Avatar).order_by(Avatar.created_at.desc(), Avatar.id)
    if not include_archived:
        query = query.where(Avatar.archived_at.is_(None))
    return list(session.scalars(query))


def archive_avatar(session: Session, avatar_id: uuid.UUID) -> Avatar:
    """Tira o avatar de novos usos sem apagar arquivo; arquivar de novo não muda nada."""
    avatar = get_avatar(session, avatar_id, for_update=True)
    if avatar.archived_at is None:
        if avatar.prepare_status == "preparando":
            raise ApiError(
                409,
                "AVATAR_PREPARING",
                "O avatar ainda está em preparação. Aguarde terminar para arquivar.",
            )
        avatar.archived_at = func.now()
    session.commit()
    session.refresh(avatar)
    return avatar


def avatar_file(
    session: Session, data_dir: Path, avatar_id: uuid.UUID, kind: AvatarFileKind
) -> tuple[Path, StoredFile]:
    file_id = getattr(get_avatar(session, avatar_id), _AVATAR_FILE_COLUMNS[kind])
    if file_id is None:
        raise ApiError(404, "NOT_FOUND", "Arquivo do avatar ainda não disponível.")
    stored = session.get(StoredFile, file_id)
    return resolve_path(data_dir, stored), stored
