"""Rotas do painel com cookie de sessão: login, sessão atual, pessoas, chaves e assets."""

import json
import math
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import AfterValidator, BaseModel, Field, StringConstraints
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from avatar_api import assets, jobs
from avatar_api.auth import (
    MIN_PASSWORD_LENGTH,
    SESSION_COOKIE,
    SESSION_COOKIE_PATH,
    CurrentPanelSession,
    DbSession,
    UserCreationError,
    authenticate,
    create_user,
    end_session,
    issue_api_key,
    new_token,
    sha256_hex,
    start_session,
)
from avatar_api.errors import ApiError
from avatar_api.job_views import (
    IdempotencyKey,
    JobCreatedOut,
    JobOut,
    WorkerStatusOut,
    download_response,
    job_created_out,
    job_out,
)
from avatar_api.jobs import _without_nul
from avatar_api.models import (
    VOICES,
    ApiKey,
    Avatar,
    RenderRecipe,
    Scene,
    StoredFile,
    User,
    UserSession,
    VideoJob,
)
from avatar_api.storage import resolve_path
from avatar_api.uploads import validate_image

router = APIRouter(prefix="/panel")

# Texto vindo do painel: NUL vira 422 aqui, antes de chegar ao PostgreSQL como erro 500.
PanelText = Annotated[str, AfterValidator(_without_nul)]
# As restrições vêm antes do validador de NUL; depois dele o pydantic deixaria de aplicá-las.
_Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(_without_nul),
]

_AssetName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    AfterValidator(_without_nul),
]


class LoginIn(BaseModel):
    username: PanelText = Field(max_length=200)
    password: PanelText = Field(max_length=1024)


class SessionUser(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str | None


class SessionOut(BaseModel):
    csrf_token: str
    expires_at: datetime
    user: SessionUser


class UserIn(BaseModel):
    username: _Name
    display_name: _Name
    password: PanelText = Field(max_length=1024)


class UserOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str | None
    created_at: datetime
    disabled_at: datetime | None


class ApiKeyIn(BaseModel):
    description: _Name


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    prefix: str
    description: str
    created_by_user_id: uuid.UUID
    created_by_username: str
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


class IssuedApiKeyOut(ApiKeyOut):
    key: str


class AvatarOut(BaseModel):
    id: uuid.UUID
    name: str
    voice: str
    status: assets.AvatarStatus
    prepare_error: str | None
    authorized_at: datetime | None
    created_at: datetime
    archived_at: datetime | None


class SceneOut(BaseModel):
    id: uuid.UUID
    name: str
    background_color: str | None
    composition: dict[str, dict[str, float]]
    status: assets.SceneStatus
    created_at: datetime
    archived_at: datetime | None


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: DbSession) -> SessionOut:
    user = authenticate(db, body.username, body.password)
    if user is None:
        raise ApiError(401, "INVALID_CREDENTIALS", "Usuário ou senha inválidos.")
    ttl_hours = request.app.state.settings.session_ttl_hours
    new = start_session(db, user, ttl_hours)
    response.set_cookie(
        SESSION_COOKIE,
        new.token,
        max_age=ttl_hours * 3600,
        path=SESSION_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return SessionOut(
        csrf_token=new.csrf_token,
        expires_at=new.row.expires_at,
        user=_session_user(user),
    )


def _session_user(user: User) -> SessionUser:
    return SessionUser(id=user.id, username=user.username, display_name=user.display_name)


@router.get("/auth/me")
def me(identity: CurrentPanelSession, db: DbSession) -> SessionOut:
    # O banco guarda só o hash do CSRF; recarregar o painel exige emitir outro, e o anterior
    # deixa de valer.
    csrf_token = new_token()
    row = db.get(UserSession, identity.session_id, with_for_update=True)
    row.csrf_hash = sha256_hex(csrf_token)
    db.commit()
    return SessionOut(
        csrf_token=csrf_token,
        expires_at=row.expires_at,
        user=_session_user(db.get(User, identity.user_id)),
    )


@router.post("/auth/logout", status_code=204)
def logout(
    response: Response,
    identity: CurrentPanelSession,
    db: DbSession,
) -> None:
    end_session(db, identity.session_id)
    response.delete_cookie(
        SESSION_COOKIE, path=SESSION_COOKIE_PATH, secure=True, httponly=True, samesite="lax"
    )


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        created_at=user.created_at,
        disabled_at=user.disabled_at,
    )


@router.get("/users")
def list_users(_: CurrentPanelSession, db: DbSession) -> list[UserOut]:
    users = db.scalars(select(User).order_by(User.created_at, User.username))
    return [_user_out(user) for user in users]


@router.post("/users", status_code=201)
def add_user(body: UserIn, _: CurrentPanelSession, db: DbSession) -> UserOut:
    try:
        user = create_user(db, body.username, body.password)
    except UserCreationError as exc:
        field = "password" if len(body.password) < MIN_PASSWORD_LENGTH else "username"
        raise ApiError(422, "VALIDATION_ERROR", str(exc), field) from exc
    user.display_name = body.display_name
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.post("/users/{user_id}/disable")
def disable_user(user_id: uuid.UUID, identity: CurrentPanelSession, db: DbSession) -> UserOut:
    if user_id == identity.user_id:
        raise ApiError(409, "CANNOT_DISABLE_SELF", "Você não pode remover o próprio acesso.")
    user = db.get(User, user_id, with_for_update=True)
    if user is None:
        raise ApiError(404, "NOT_FOUND", "Pessoa não encontrada.")
    if user.disabled_at is None:
        user.disabled_at = func.now()
    # Na mesma transação: nenhuma sessão aberta dela sobrevive à remoção do acesso.
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    db.commit()
    db.refresh(user)
    return _user_out(user)


def _key_out(key: ApiKey, username: str) -> ApiKeyOut:
    return ApiKeyOut(
        id=key.id,
        prefix=key.prefix,
        description=key.description,
        created_by_user_id=key.created_by_user_id,
        created_by_username=username,
        created_at=key.created_at,
        revoked_at=key.revoked_at,
        last_used_at=key.last_used_at,
    )


def _load_key(db: Session, key_id: uuid.UUID) -> ApiKeyOut:
    found = db.execute(
        select(ApiKey, User.username)
        .join(User, User.id == ApiKey.created_by_user_id)
        .where(ApiKey.id == key_id)
    ).one_or_none()
    if found is None:
        raise ApiError(404, "NOT_FOUND", "Chave de API não encontrada.")
    return _key_out(*found)


@router.get("/api-keys")
def list_api_keys(_: CurrentPanelSession, db: DbSession) -> list[ApiKeyOut]:
    rows = db.execute(
        select(ApiKey, User.username)
        .join(User, User.id == ApiKey.created_by_user_id)
        .order_by(ApiKey.created_at.desc(), ApiKey.id)
    ).all()
    return [_key_out(key, username) for key, username in rows]


@router.post("/api-keys", status_code=201)
def create_api_key(
    body: ApiKeyIn,
    identity: CurrentPanelSession,
    db: DbSession,
) -> IssuedApiKeyOut:
    issued = issue_api_key(db, identity.user_id, body.description)
    # A chave completa sai só nesta resposta; depois disso só o prefixo existe.
    return IssuedApiKeyOut(**_load_key(db, issued.row.id).model_dump(), key=issued.key)


@router.post("/api-keys/{key_id}/revoke")
def revoke_api_key(
    key_id: uuid.UUID,
    _: CurrentPanelSession,
    db: DbSession,
) -> ApiKeyOut:
    key = db.get(ApiKey, key_id, with_for_update=True)
    if key is None:
        raise ApiError(404, "NOT_FOUND", "Chave de API não encontrada.")
    if key.revoked_at is None:
        key.revoked_at = func.now()
    db.commit()
    return _load_key(db, key_id)


# --- avatares ---------------------------------------------------------------------------


def _avatar_out(avatar: Avatar) -> AvatarOut:
    return AvatarOut(
        id=avatar.id,
        name=avatar.name,
        voice=avatar.voice,
        status=assets.avatar_status(avatar),
        prepare_error=avatar.prepare_error,
        authorized_at=avatar.authorized_at,
        created_at=avatar.created_at,
        archived_at=avatar.archived_at,
    )


@router.get("/avatars")
def list_avatars(
    _: CurrentPanelSession, db: DbSession, include_archived: bool = False
) -> list[AvatarOut]:
    return [_avatar_out(avatar) for avatar in assets.list_avatars(db, include_archived)]


@router.post("/avatars", status_code=201)
def create_avatar(
    name: Annotated[_AssetName, Form()],
    file: Annotated[UploadFile, File()],
    identity: CurrentPanelSession,
    db: DbSession,
    request: Request,
    voice: Annotated[str | None, Form()] = None,
    authorization_confirmed: Annotated[bool | None, Form()] = None,
) -> AvatarOut:
    if voice not in VOICES:
        raise ApiError(422, "VALIDATION_ERROR", "Escolha a voz do avatar.", "voice")
    if authorization_confirmed is not True:
        raise ApiError(
            422, "VALIDATION_ERROR", "Confirme a autorização de uso da imagem.", "authorization"
        )
    # O temporário da validação fica fora de DATA_DIR: recusa não deixa nada no volume.
    with tempfile.TemporaryDirectory(prefix="avatar-upload-") as tmp_dir:
        image = validate_image(file.file, "file", Path(tmp_dir))
        avatar = assets.create_avatar(
            db, request.app.state.settings.data_dir, identity.user_id, name, voice, image
        )
    return _avatar_out(avatar)


# Sem PUT nem PATCH: asset salvo não muda; para trocar, arquiva e cadastra outro.
@router.get("/avatars/{avatar_id}")
def get_avatar(avatar_id: uuid.UUID, _: CurrentPanelSession, db: DbSession) -> AvatarOut:
    return _avatar_out(assets.get_avatar(db, avatar_id))


@router.post("/avatars/{avatar_id}/archive")
def archive_avatar(avatar_id: uuid.UUID, _: CurrentPanelSession, db: DbSession) -> AvatarOut:
    return _avatar_out(assets.archive_avatar(db, avatar_id))


@router.get("/avatars/{avatar_id}/files/{kind}")
def avatar_file(
    avatar_id: uuid.UUID,
    kind: assets.AvatarFileKind,
    _: CurrentPanelSession,
    db: DbSession,
    request: Request,
) -> FileResponse:
    path, stored = assets.avatar_file(db, request.app.state.settings.data_dir, avatar_id, kind)
    return FileResponse(path, media_type=stored.content_type, headers={"Cache-Control": "private"})


# --- cenários ---------------------------------------------------------------------------


def _scene_out(scene: Scene) -> SceneOut:
    return SceneOut(
        id=scene.id,
        name=scene.name,
        background_color=scene.background_color,
        composition=scene.composition,
        status=assets.scene_status(scene),
        created_at=scene.created_at,
        archived_at=scene.archived_at,
    )


@router.get("/scenes")
def list_scenes(
    _: CurrentPanelSession, db: DbSession, include_archived: bool = False
) -> list[SceneOut]:
    return [_scene_out(scene) for scene in assets.list_scenes(db, include_archived)]


@router.post("/scenes", status_code=201)
def create_scene(
    name: Annotated[_AssetName, Form()],
    composition: Annotated[str, Form()],
    identity: CurrentPanelSession,
    db: DbSession,
    request: Request,
    background_color: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> SceneOut:
    if (background_color is None) == (file is None):
        raise ApiError(
            422, "VALIDATION_ERROR", "Escolha uma imagem ou uma cor de fundo.", "background"
        )
    if background_color is not None and not assets.HEX_COLOR.fullmatch(background_color):
        raise ApiError(
            422, "VALIDATION_ERROR", "Use uma cor no formato #RRGGBB.", "background_color"
        )
    framing = assets.parse_composition(composition)
    data_dir = request.app.state.settings.data_dir
    if file is None:
        scene = assets.create_scene(
            db, data_dir, identity.user_id, name, framing, background_color=background_color
        )
        return _scene_out(scene)
    # O temporário da validação fica fora de DATA_DIR: recusa não deixa nada no volume.
    with tempfile.TemporaryDirectory(prefix="scene-upload-") as tmp_dir:
        image = validate_image(file.file, "file", Path(tmp_dir))
        scene = assets.create_scene(db, data_dir, identity.user_id, name, framing, image=image)
    return _scene_out(scene)


# Sem PUT nem PATCH: cenário salvo não muda; para trocar, arquiva e cadastra outro.
@router.post("/scenes/{scene_id}/archive")
def archive_scene(scene_id: uuid.UUID, _: CurrentPanelSession, db: DbSession) -> SceneOut:
    return _scene_out(assets.archive_scene(db, scene_id))


@router.get("/scenes/{scene_id}/files/{kind}")
def scene_file(
    scene_id: uuid.UUID,
    kind: assets.SceneFileKind,
    _: CurrentPanelSession,
    db: DbSession,
    request: Request,
) -> FileResponse:
    path, stored = assets.scene_file(db, request.app.state.settings.data_dir, scene_id, kind)
    return FileResponse(path, media_type=stored.content_type, headers={"Cache-Control": "private"})


# --- geração e histórico: equipe única da organização (AD-004) --------------------------


class GenerationConfigOut(BaseModel):
    max_script_chars: int | None
    max_audio_seconds: float | None
    chars_per_second: float | None


@router.get("/generation-config")
def generation_config(_: CurrentPanelSession, db: DbSession) -> GenerationConfigOut:
    recipe = db.scalar(select(RenderRecipe).where(RenderRecipe.is_current))
    limits = recipe.spec.get("limits", {}) if recipe else {}
    return GenerationConfigOut(
        max_script_chars=recipe.max_script_chars if recipe else None,
        max_audio_seconds=limits.get("max_audio_seconds"),
        chars_per_second=limits.get("chars_per_second"),
    )


@router.get("/worker-status")
def video_worker_status(_: CurrentPanelSession, db: DbSession) -> WorkerStatusOut:
    return WorkerStatusOut(last_heartbeat_at=jobs.last_video_worker_heartbeat(db))


class PanelJobOut(JobOut):
    script_text: str
    avatar_id: uuid.UUID
    scene_id: uuid.UUID
    avatar_name: str
    scene_name: str
    voice: str
    origin: str
    requested_by: str
    started_at: datetime | None
    file_exists: bool
    size_bytes: int | None
    duration_seconds: float | None


def _panel_job_out(db: Session, job: VideoJob, data_dir: Path) -> PanelJobOut:
    avatar = db.get(Avatar, job.avatar_id)
    scene = db.get(Scene, job.scene_id)
    person = db.get(User, job.requested_by_user_id) if job.requested_by_user_id else None
    key = db.get(ApiKey, job.api_key_id) if job.api_key_id else None
    stored = db.get(StoredFile, job.result_file_id) if job.result_file_id else None
    file_exists = (
        job.status == "ready" and stored is not None and resolve_path(data_dir, stored).is_file()
    )
    duration = None
    if file_exists:
        manifest = db.scalar(
            select(StoredFile).where(
                StoredFile.attempt_id == job.current_attempt_id, StoredFile.name == "manifest.json"
            )
        )
        if manifest:
            try:
                measured = json.loads(resolve_path(data_dir, manifest).read_text())["audio_seconds"]
                if isinstance(measured, (int, float)) and math.isfinite(measured) and measured > 0:
                    duration = measured
            except (OSError, ValueError, KeyError, TypeError):
                # Tentativas antigas sem manifesto não recebem duração fictícia.
                pass
    output = job_out(job, "/panel").model_dump()
    if not file_exists:
        output["download_url"] = None
    return PanelJobOut(
        **output,
        script_text=job.script_text,
        avatar_id=job.avatar_id,
        scene_id=job.scene_id,
        avatar_name=avatar.name,
        scene_name=scene.name,
        voice=job.voice,
        origin=job.origin,
        requested_by=(person.display_name or person.username) if person else key.description,
        started_at=job.started_at,
        file_exists=file_exists,
        size_bytes=stored.size_bytes if file_exists else None,
        duration_seconds=duration,
    )


@router.post("/jobs", status_code=202)
def create_panel_job(
    body: jobs.NewVideoJob,
    identity: CurrentPanelSession,
    db: DbSession,
    idempotency_key: IdempotencyKey = None,
) -> JobCreatedOut:
    job = jobs.create_video_job(
        db,
        jobs.JobRequester(origin="panel", user_id=identity.user_id),
        body,
        idempotency_key,
    )
    return job_created_out(job, "/panel")


@router.get("/jobs")
def list_panel_jobs(_: CurrentPanelSession, db: DbSession, request: Request) -> list[PanelJobOut]:
    return [
        _panel_job_out(db, job, request.app.state.settings.data_dir)
        for job in db.scalars(select(VideoJob).order_by(VideoJob.created_at.desc(), VideoJob.id))
    ]


def _panel_job(db: Session, job_id: uuid.UUID) -> VideoJob:
    job = db.get(VideoJob, job_id)
    if job is None:
        raise ApiError(404, "NOT_FOUND", "Job não encontrado.")
    return job


@router.get("/jobs/{job_id}")
def get_panel_job(
    job_id: uuid.UUID, _: CurrentPanelSession, db: DbSession, request: Request
) -> PanelJobOut:
    return _panel_job_out(db, _panel_job(db, job_id), request.app.state.settings.data_dir)


@router.get("/jobs/{job_id}/download")
def download_panel_job(
    job_id: uuid.UUID, _: CurrentPanelSession, db: DbSession, request: Request
) -> FileResponse:
    return download_response(db, _panel_job(db, job_id), request.app.state.settings.data_dir)
