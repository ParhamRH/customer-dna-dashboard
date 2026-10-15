"""Production refuses to start with development secrets."""
from __future__ import annotations

import pytest

from app.config import get_settings


@pytest.fixture
def fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_production_requires_real_secrets(monkeypatch, fresh_settings):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("BDNA_ENVIRONMENT", "production")
    monkeypatch.setenv("BDNA_SECRET_KEY", "CHANGE-ME-CHANGE-ME-CHANGE-ME-CHANGE-ME")
    monkeypatch.setenv("BDNA_ENCRYPTION_KEY", "")
    with pytest.raises(RuntimeError) as e:
        get_settings()
    assert "BDNA_SECRET_KEY" in str(e.value) and "BDNA_ENCRYPTION_KEY" in str(e.value)
    get_settings.cache_clear()
    monkeypatch.setenv("BDNA_SECRET_KEY", "k" * 48)
    monkeypatch.setenv("BDNA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert get_settings().is_production


def test_development_allows_derived_keys(monkeypatch, fresh_settings):
    monkeypatch.setenv("BDNA_ENVIRONMENT", "development")
    monkeypatch.setenv("BDNA_ENCRYPTION_KEY", "")
    assert get_settings().environment == "development"
