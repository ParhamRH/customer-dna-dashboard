"""Shared API helpers: pagination, slugs, ORM → dict serialization."""
from __future__ import annotations

import datetime as dt
import decimal
import re
import unicodedata
import uuid
from typing import Annotated, Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class PageParams(BaseModel):
    limit: int = 50
    offset: int = 0


def page_params(
    limit: Annotated[int, Query(ge=1, le=500)] = 50, offset: Annotated[int, Query(ge=0)] = 0
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


def paginate(db: Session, stmt: Select, params: PageParams, mapper=None) -> dict[str, Any]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.execute(stmt.limit(params.limit).offset(params.offset)).scalars().all()
    items = [mapper(r) if mapper else r for r in rows]
    return {"items": items, "total": total, "limit": params.limit, "offset": params.offset}


def slugify(value: str, max_len: int = 80) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return (value or "item")[:max_len].strip("-")


def jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [jsonable(v) for v in value]
    return value


def row_to_dict(obj: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    """Serialize an ORM instance's column attributes to JSON-safe primitives."""
    exclude = (exclude or set()) | {"search_tsv"}
    mapper = inspect(obj).mapper
    return {
        attr.key: jsonable(getattr(obj, attr.key))
        for attr in mapper.column_attrs
        if attr.key not in exclude
    }


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
