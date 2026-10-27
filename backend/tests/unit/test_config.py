"""Unit tests for centralized configuration loading."""

from app.core.config import Settings, get_settings


def test_settings_load():
    """Verify settings instantiate with valid defaults."""
    settings = get_settings()
    assert settings.APP_NAME == "CraftFlow"
    assert settings.APP_VERSION == "0.1.0"
    assert settings.LOG_LEVEL == "INFO"
    assert settings.is_testing is True
    assert settings.is_production is False


def test_cors_origins_parsing():
    """Verify CORS origins string or list parsing."""
    s1 = Settings(CORS_ORIGINS=["http://localhost:3000"])
    assert "http://localhost:3000" in s1.CORS_ORIGINS

    s2 = Settings(CORS_ORIGINS="http://example.com, http://test.com")
    assert "http://example.com" in s2.CORS_ORIGINS
    assert "http://test.com" in s2.CORS_ORIGINS
