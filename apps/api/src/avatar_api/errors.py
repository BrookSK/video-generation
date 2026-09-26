import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)

_LOCATION_PARTS = {"body", "query", "path", "header", "cookie"}

_HTTP_CODES = {
    400: ("BAD_REQUEST", "Requisição inválida."),
    401: ("UNAUTHORIZED", "Autenticação necessária."),
    403: ("FORBIDDEN", "Acesso negado."),
    404: ("NOT_FOUND", "Recurso não encontrado."),
    405: ("METHOD_NOT_ALLOWED", "Método não permitido para este recurso."),
    413: ("PAYLOAD_TOO_LARGE", "Conteúdo maior que o permitido."),
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    field: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, str] = {"code": code, "message": message}
    if field is not None:
        body["field"] = field
    request_id = getattr(request.state, "request_id", "")
    body["request_id"] = request_id
    # O handler de Exception roda fora do middleware, então o cabeçalho é posto aqui também.
    headers = {**(headers or {}), "X-Request-ID": request_id}
    return JSONResponse({"error": body}, status_code=status, headers=headers)


async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(request, exc.status, exc.code, exc.message, exc.field)


async def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
    code, message = _HTTP_CODES.get(
        exc.status_code, (HTTPStatus(exc.status_code).name, "Erro na requisição.")
    )
    return error_response(request, exc.status_code, code, message, headers=exc.headers)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    field = None
    if errors:
        loc = [str(part) for part in errors[0].get("loc", ()) if part not in _LOCATION_PARTS]
        field = ".".join(loc) or None
    return error_response(request, 422, "VALIDATION_ERROR", "Dados inválidos na requisição.", field)


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "erro interno não tratado",
        extra={"request_id": getattr(request.state, "request_id", "")},
    )
    return error_response(request, 500, "INTERNAL_ERROR", "Erro interno no servidor.")


async def _database_error(request: Request, exc: DBAPIError) -> JSONResponse:
    # Banco inalcançável ou conexão perdida vira 503; outros erros do banco seguem como 500.
    if not (isinstance(exc, OperationalError) or exc.connection_invalidated):
        # Só tipo e sqlstate vão para o log: o DETAIL do PostgreSQL ("Failing row contains")
        # pode trazer valores da linha, como o texto da fala.
        logger.error(
            "erro de banco de dados (%s, sqlstate %s)",
            type(exc.orig).__name__,
            getattr(exc.orig, "sqlstate", None),
            extra={"request_id": getattr(request.state, "request_id", "")},
        )
        return error_response(request, 500, "INTERNAL_ERROR", "Erro interno no servidor.")
    # Só o tipo vai para o log: o texto do driver traz host, porta e usuário.
    logger.warning(
        "banco de dados indisponível (%s)",
        type(exc.orig).__name__,
        extra={"request_id": getattr(request.state, "request_id", "")},
    )
    return error_response(
        request,
        503,
        "SERVICE_UNAVAILABLE",
        "Serviço temporariamente indisponível. Tente novamente em instantes.",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    # OperationalError é subclasse de DBAPIError; o mesmo handler cobre as duas.
    app.add_exception_handler(DBAPIError, _database_error)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled_error)
