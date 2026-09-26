"""Rotas do painel com cookie de sessão: login, logout e chaves de API."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from avatar_api.auth import (
    SESSION_COOKIE,
    SESSION_COOKIE_PATH,
    CurrentPanelSession,
    DbSession,
    authenticate,
    end_session,
    issue_api_key,
    start_session,
)
from avatar_api.errors import ApiError
from avatar_api.models import ApiKey, User

router = APIRouter(prefix="/panel")


class LoginIn(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=1024)


class LoginUser(BaseModel):
    id: uuid.UUID
    username: str


class LoginOut(BaseModel):
    csrf_token: str
    expires_at: datetime
    user: LoginUser


class ApiKeyIn(BaseModel):
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]


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


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: DbSession) -> LoginOut:
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
    return LoginOut(
        csrf_token=new.csrf_token,
        expires_at=new.row.expires_at,
        user=LoginUser(id=user.id, username=user.username),
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
