"""Senhas, sessões do painel, CSRF e chaves de API.

Nenhum segredo (senha, token de sessão, token CSRF ou chave) é gravado em banco ou em log:
o banco guarda só hashes e toda conferência de segredo usa comparação em tempo constante.
"""

import hashlib
import hmac
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from functools import cache
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from avatar_api.db import get_session
from avatar_api.errors import ApiError
from avatar_api.models import ApiKey, User, UserSession

DbSession = Annotated[Session, Depends(get_session)]

MIN_PASSWORD_LENGTH = 12
SESSION_COOKIE = "avatar_session"
SESSION_COOKIE_PATH = "/panel"
CSRF_HEADER = "X-CSRF-Token"
API_KEY_PREFIX = "avk_"
API_KEY_VISIBLE_CHARS = 12
TOKEN_BYTES = 32

# avk_ + base64url sem preenchimento de 32 bytes (43 caracteres).
_API_KEY_PATTERN = re.compile(r"avk_[A-Za-z0-9_-]{43}")
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Argon2id é o tipo padrão do PasswordHasher do argon2-cffi.
_password_hasher = PasswordHasher()


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _same_hash(value: str, expected_hash: str) -> bool:
    return hmac.compare_digest(sha256_hex(value), expected_hash)


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


# --- senhas ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@cache
def _dummy_password_hash() -> str:
    return hash_password(new_token())


class UserCreationError(Exception):
    """Falha de criação de usuário com mensagem em português pronta para o operador."""


def create_user(db: Session, username: str, password: str) -> User:
    username = username.strip()
    if not username:
        raise UserCreationError("Informe um nome de usuário.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise UserCreationError(f"A senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise UserCreationError(f"Já existe um usuário com o nome {username}.") from exc
    return user


def authenticate(db: Session, username: str, password: str) -> User | None:
    """Devolve o usuário ativo com essa senha, ou None sem dizer o motivo."""
    user = db.scalar(select(User).where(User.username == username))
    # Usuário inexistente ainda paga o custo do argon2, para o tempo não revelar se ele existe.
    password_ok = verify_password(user.password_hash if user else _dummy_password_hash(), password)
    if user is None or not password_ok or user.disabled_at is not None:
        return None
    return user


# --- sessões do painel e CSRF ---------------------------------------------------------


@dataclass(frozen=True)
class NewSession:
    token: str
    csrf_token: str
    row: UserSession


@dataclass(frozen=True)
class PanelIdentity:
    session_id: uuid.UUID
    user_id: uuid.UUID
    username: str


def start_session(db: Session, user: User, ttl_hours: int) -> NewSession:
    token, csrf_token = new_token(), new_token()
    row = UserSession(
        user_id=user.id,
        token_hash=sha256_hex(token),
        csrf_hash=sha256_hex(csrf_token),
        expires_at=func.now() + timedelta(hours=ttl_hours),
    )
    db.add(row)
    db.commit()
    return NewSession(token=token, csrf_token=csrf_token, row=row)


def require_session(request: Request, db: DbSession) -> PanelIdentity:
    """Exige cookie de sessão vigente e, em mutações, o cabeçalho X-CSRF-Token da sessão."""
    token = request.cookies.get(SESSION_COOKIE)
    found = None
    if token:
        found = db.execute(
            select(UserSession.id, UserSession.csrf_hash, User.id, User.username)
            .join(User, User.id == UserSession.user_id)
            .where(
                UserSession.token_hash == sha256_hex(token),
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > func.now(),
                User.disabled_at.is_(None),
            )
        ).one_or_none()
    if found is None:
        raise ApiError(401, "UNAUTHORIZED", "Sessão ausente ou expirada. Entre novamente.")
    session_id, csrf_hash, user_id, username = found
    if request.method not in _SAFE_METHODS:
        csrf_token = request.headers.get(CSRF_HEADER, "")
        if not csrf_token or not _same_hash(csrf_token, csrf_hash):
            raise ApiError(403, "CSRF_INVALID", "Token CSRF ausente ou inválido.")
    return PanelIdentity(session_id=session_id, user_id=user_id, username=username)


def end_session(db: Session, session_id: uuid.UUID) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.id == session_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    db.commit()


# --- chaves de API --------------------------------------------------------------------


@dataclass(frozen=True)
class IssuedApiKey:
    key: str
    row: ApiKey


def issue_api_key(db: Session, user_id: uuid.UUID, description: str) -> IssuedApiKey:
    key = API_KEY_PREFIX + new_token()
    row = ApiKey(
        prefix=key[:API_KEY_VISIBLE_CHARS],
        key_hash=sha256_hex(key),
        description=description,
        created_by_user_id=user_id,
    )
    db.add(row)
    db.commit()
    return IssuedApiKey(key=key, row=row)


def _unauthorized() -> ApiError:
    # Um único erro para ausência, formato errado, chave desconhecida ou revogada.
    return ApiError(401, "UNAUTHORIZED", "Chave de API ausente ou inválida.")


def require_api_key(request: Request, db: DbSession) -> ApiKey:
    """Aceita só `Authorization: Bearer <chave>` com chave vigente e registra o uso."""
    scheme, _, key = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not _API_KEY_PATTERN.fullmatch(key):
        raise _unauthorized()
    row = db.scalar(select(ApiKey).where(ApiKey.prefix == key[:API_KEY_VISIBLE_CHARS]))
    # Sem linha, compara contra um hash qualquer para o tempo não revelar o prefixo.
    hash_ok = _same_hash(key, row.key_hash if row else sha256_hex(new_token()))
    if row is None or not hash_ok or row.revoked_at is not None:
        raise _unauthorized()
    row.last_used_at = func.now()
    db.commit()
    return row


CurrentPanelSession = Annotated[PanelIdentity, Depends(require_session)]
CurrentApiKey = Annotated[ApiKey, Depends(require_api_key)]
