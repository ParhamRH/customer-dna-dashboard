"""Uniform API error model: {"error": {"code", "message", "details"}}."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError


class ApiError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: Any = None, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFound(ApiError):
    status_code = 404
    code = "not_found"


class Forbidden(ApiError):
    status_code = 403
    code = "forbidden"


class Unauthorized(ApiError):
    status_code = 401
    code = "unauthorized"


class Conflict(ApiError):
    status_code = 409
    code = "conflict"


class ValidationFailed(ApiError):
    status_code = 422
    code = "validation_failed"


def _body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()
        ]
        return JSONResponse(_body("validation_failed", "Request validation failed", details), status_code=422)

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        diag = getattr(getattr(exc, "orig", None), "diag", None)
        constraint = getattr(diag, "constraint_name", None)
        msg = getattr(diag, "message_primary", None) or "Integrity constraint violated"
        return JSONResponse(_body("conflict", msg, {"constraint": constraint}), status_code=409)

    @app.exception_handler(DBAPIError)
    async def _dbapi(_: Request, exc: DBAPIError) -> JSONResponse:
        diag = getattr(getattr(exc, "orig", None), "diag", None)
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
        # 42501 = insufficient_privilege / RLS violation, 23xxx = integrity
        if sqlstate == "42501":
            return JSONResponse(_body("forbidden", "Operation not permitted for this tenant"), status_code=403)
        if sqlstate and sqlstate.startswith("23"):
            msg = getattr(diag, "message_primary", None) or "Integrity constraint violated"
            return JSONResponse(_body("conflict", msg), status_code=409)
        return JSONResponse(_body("database_error", "Database error"), status_code=500)
