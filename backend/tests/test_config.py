from app.config import Settings


def test_default_cors_origins_allow_supported_local_frontend_hosts(
    monkeypatch,
) -> None:
    monkeypatch.delenv("BACKEND_CORS_ORIGINS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.cors_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
