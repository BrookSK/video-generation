"""Comando `avatar-api` de administração da instalação."""

import argparse
import getpass
import sys

from sqlalchemy.orm import Session

from avatar_api.auth import UserCreationError, create_user
from avatar_api.config import Settings
from avatar_api.db import create_db_engine


def _read_password(from_stdin: bool) -> str | None:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    password = getpass.getpass("Senha: ")
    if getpass.getpass("Confirme a senha: ") != password:
        return None
    return password


def _users_create(args: argparse.Namespace) -> int:
    database_url = Settings.from_env().database_url
    if not database_url:
        print("Erro: defina DATABASE_URL para acessar o banco.", file=sys.stderr)
        return 1
    password = _read_password(args.password_stdin)
    if password is None:
        print("Erro: as senhas digitadas não conferem.", file=sys.stderr)
        return 1
    engine = create_db_engine(database_url)
    try:
        with Session(engine, expire_on_commit=False) as db:
            user = create_user(db, args.username, password)
    except UserCreationError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print(f"Usuário {user.username} criado.")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="avatar-api", description="Administração da API.")
    commands = parser.add_subparsers(dest="command", required=True)
    users = commands.add_parser("users", help="Usuários do painel.")
    users_commands = users.add_subparsers(dest="users_command", required=True)
    create = users_commands.add_parser("create", help="Cria um usuário do painel.")
    create.add_argument("--username", required=True, help="Nome de usuário.")
    create.add_argument(
        "--password-stdin",
        action="store_true",
        help="Lê a senha da primeira linha da entrada padrão em vez de perguntar.",
    )
    create.set_defaults(handler=_users_create)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
