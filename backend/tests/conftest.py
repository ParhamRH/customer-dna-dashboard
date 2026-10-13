"""Test harness.

Runs against a REAL PostgreSQL database (bdna_test) with the real roles, because Row Level
Security can only be tested on the database itself. The schema is rebuilt from migrations at
the start of the session. Fixtures create three fictional customers (A, B, C).
"""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="bdna-test-"))
DB = os.environ.get("BDNA_TEST_DB", "bdna_test")
HOST = os.environ.get("BDNA_TEST_DB_HOST", "localhost")
os.environ.update(
    {
        "BDNA_ENVIRONMENT": "test",
        "BDNA_SECRET_KEY": "test-secret-key-for-unit-tests-only",
        "BDNA_DATABASE_OWNER_URL": f"postgresql+psycopg://bdna_owner:bdna_owner@{HOST}:5432/{DB}",
        "BDNA_DATABASE_APP_URL": f"postgresql+psycopg://bdna_app:bdna_app@{HOST}:5432/{DB}",
        "BDNA_DATABASE_SYSTEM_URL": f"postgresql+psycopg://bdna_system:bdna_system@{HOST}:5432/{DB}",
        "BDNA_STORAGE_BACKEND": "local",
        "BDNA_STORAGE_LOCAL_ROOT": str(_TMP / "storage"),
        "BDNA_AI_VISION_PROVIDER": "dev",
        "BDNA_AI_TEXT_PROVIDER": "dev",
        "BDNA_AI_EMBEDDING_PROVIDER": "dev",
    }
)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()
BACKEND = Path(__file__).resolve().parents[1]


def _migrate() -> None:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _database():
    from app.db.session import dispose_engines
    from app.security.permissions import reset_cache

    dispose_engines()
    _migrate()
    reset_cache()
    yield
    dispose_engines()
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def app(_database):
    from app.main import create_app

    return create_app()


class Api:
    """Thin wrapper around TestClient that carries a bearer token and workspace header."""

    def __init__(self, client: TestClient, token: str | None = None, org: str | None = None):
        self.client, self.token, self.org = client, token, org

    def _headers(self, extra: dict | None = None) -> dict:
        h = {}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.org:
            h["X-Organization-Id"] = self.org
        h.update(extra or {})
        return h

    def for_org(self, org: str | None) -> "Api":
        return Api(self.client, self.token, org)

    def get(self, url, **kw):
        return self.client.get(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def post(self, url, **kw):
        return self.client.post(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def patch(self, url, **kw):
        return self.client.patch(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def put(self, url, **kw):
        return self.client.put(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def delete(self, url, **kw):
        return self.client.delete(url, headers=self._headers(kw.pop("headers", None)), **kw)


@dataclass
class Customer:
    org_id: str
    slug: str
    brand_id: str
    admin: Api
    users: dict[str, Api]  # role -> Api client


def login(client: TestClient, email: str, password: str) -> str:
    r = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    client.cookies.clear()
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def client(app) -> TestClient:
    with TestClient(app) as c:
        yield c


PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session")
def platform_admin(client) -> Api:
    from app.services.accounts import create_platform_admin

    create_platform_admin("root@platform.test", "Platform Root", PASSWORD)
    return Api(client, login(client, "root@platform.test", PASSWORD))


def _make_customer(client, platform_admin: Api, letter: str) -> Customer:
    slug = f"customer-{letter.lower()}-{uuid.uuid4().hex[:6]}"
    r = platform_admin.post(
        "/v1/organizations",
        json={
            "name": f"Customer {letter}",
            "slug": slug,
            "first_brand_name": f"Brand {letter}",
            "admin_email": f"admin@{slug}.test",
            "admin_password": PASSWORD,
            "industry": "Design",
        },
    )
    assert r.status_code == 201, r.text
    data = r.json()
    admin = Api(client, login(client, f"admin@{slug}.test", PASSWORD), data["organization_id"])
    users = {"customer_admin": admin}
    for role in ("creative_director", "editor", "reviewer", "viewer"):
        email = f"{role}@{slug}.test"
        rr = admin.post("/v1/workspace/members", json={"email": email, "role": role, "password": PASSWORD})
        assert rr.status_code == 201, rr.text
        users[role] = Api(client, login(client, email, PASSWORD), data["organization_id"])
    return Customer(data["organization_id"], slug, data["brand_id"], admin, users)


@pytest.fixture(scope="session")
def customers(client, platform_admin) -> dict[str, Customer]:
    return {letter: _make_customer(client, platform_admin, letter) for letter in ("A", "B", "C")}
