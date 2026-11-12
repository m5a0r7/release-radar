from radar.config import Settings


def test_blank_secrets_are_treated_as_unset() -> None:
    settings = Settings(github_token="", anthropic_api_key="  ")

    assert settings.github_token is None
    assert settings.anthropic_api_key is None


def test_secrets_are_not_exposed_in_repr() -> None:
    settings = Settings(github_token="ghp_supersecret")

    assert "ghp_supersecret" not in repr(settings)
