import pytest

from app.auth import hash_password, session_secret, verify_password
from app.auth import ADMIN_PASSWORD_HASH_ENV
from scripts.seed import reset_database


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    password_hash = hash_password("secret")

    assert password_hash != "secret"
    assert verify_password("secret", password_hash)
    assert not verify_password("wrong", password_hash)


def test_production_requires_explicit_session_secret(monkeypatch) -> None:
    monkeypatch.setenv("BATTLE_MARCH_ENV", "production")
    monkeypatch.delenv("BATTLE_MARCH_SESSION_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="BATTLE_MARCH_SESSION_SECRET"):
        session_secret()


def test_seed_reset_refuses_to_run_in_production(monkeypatch) -> None:
    monkeypatch.setenv("BATTLE_MARCH_ENV", "production")

    with pytest.raises(RuntimeError, match="Refusing to reset"):
        reset_database()


def test_admin_hash_env_name_is_stable() -> None:
    assert ADMIN_PASSWORD_HASH_ENV == "BATTLE_MARCH_ADMIN_PASSWORD_HASH"
