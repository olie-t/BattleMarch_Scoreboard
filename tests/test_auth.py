import pytest

from app.auth import hash_password, session_secret, verify_password


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
