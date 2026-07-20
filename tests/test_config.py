import pytest

from load_balancer.config import DEFAULT_BACKENDS, parse_settings
from load_balancer.routing import Backend


def test_uses_local_demonstration_defaults() -> None:
    settings = parse_settings([])

    assert settings.listen_host == "127.0.0.1"
    assert settings.listen_port == 8080
    assert settings.backends == DEFAULT_BACKENDS
    assert settings.health_path == "/health"
    assert settings.health_interval == 2.0
    assert settings.health_timeout == 0.5


def test_accepts_custom_listener_and_repeated_backends() -> None:
    settings = parse_settings(
        [
            "--listen-host",
            "0.0.0.0",
            "--listen-port",
            "8088",
            "--health-path",
            "/ready",
            "--health-interval",
            "5",
            "--health-timeout",
            "1.25",
            "--backend",
            "api-a=http://10.0.0.1:9000",
            "--backend",
            "api-b=http://10.0.0.2:9000/",
        ]
    )

    assert settings.listen_host == "0.0.0.0"
    assert settings.listen_port == 8088
    assert settings.health_path == "/ready"
    assert settings.health_interval == 5.0
    assert settings.health_timeout == 1.25
    assert settings.backends == (
        Backend("api-a", "http://10.0.0.1:9000"),
        Backend("api-b", "http://10.0.0.2:9000"),
    )


@pytest.mark.parametrize(
    "backend",
    [
        "missing-separator",
        "=http://127.0.0.1:9001",
        "api=https://127.0.0.1:9001",
        "api=http://127.0.0.1:9001/nested-path",
    ],
)
def test_rejects_invalid_backend_definitions(backend: str) -> None:
    with pytest.raises(SystemExit):
        parse_settings(["--backend", backend])


def test_rejects_invalid_port() -> None:
    with pytest.raises(SystemExit):
        parse_settings(["--listen-port", "70000"])


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_rejects_invalid_health_timing(value: str) -> None:
    with pytest.raises(SystemExit):
        parse_settings(["--health-interval", value])


@pytest.mark.parametrize("value", ["health", "//health"])
def test_rejects_invalid_health_path(value: str) -> None:
    with pytest.raises(SystemExit):
        parse_settings(["--health-path", value])


def test_rejects_duplicate_backend_names() -> None:
    with pytest.raises(SystemExit):
        parse_settings(
            [
                "--backend",
                "api=http://127.0.0.1:9001",
                "--backend",
                "api=http://127.0.0.1:9002",
            ]
        )
