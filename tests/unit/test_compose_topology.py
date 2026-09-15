import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
COMPOSE = PROJECT_ROOT.joinpath("docker-compose.yml").read_text(encoding="utf-8")


def service_block(name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-z][a-z0-9_-]*:\n|^volumes:|\Z)",
        COMPOSE,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Compose service is missing: {name}"
    return match.group("body")


def test_compose_contains_complete_ordered_production_topology() -> None:
    for service in ("db", "backup", "migrate", "bot", "web", "miniapp"):
        service_block(service)

    miniapp = service_block("miniapp")
    assert "context: ./frontend" in miniapp
    assert "target: runtime" in miniapp
    assert "web:\n        condition: service_healthy" in miniapp
    assert "MINIAPP_DOMAIN: ${MINIAPP_DOMAIN:-localhost}" in miniapp


def test_only_miniapp_publishes_public_ports() -> None:
    miniapp = service_block("miniapp")
    assert '- "80:80"' in miniapp
    assert '- "443:443"' in miniapp
    assert '- "443:443/udp"' in miniapp

    db = service_block("db")
    assert '"127.0.0.1:${POSTGRES_PORT:-5432}:5432"' in db
    for service in ("backup", "migrate", "bot", "web"):
        assert "\n    ports:" not in service_block(service)
    assert "8080:8080" not in COMPOSE


def test_caddy_state_uses_persistent_named_volumes() -> None:
    miniapp = service_block("miniapp")
    assert "caddy_data:/data" in miniapp
    assert "caddy_config:/config" in miniapp
    assert "\n  caddy_data:" in COMPOSE
    assert "\n  caddy_config:" in COMPOSE
    assert "postgres_data:/var/lib/postgresql/data" in service_block("db")
    assert "postgres_backups:/backups" in service_block("backup")


def test_miniapp_runtime_is_hardened_and_has_rotated_logs() -> None:
    miniapp = service_block("miniapp")
    assert "read_only: true" in miniapp
    assert "no-new-privileges:true" in miniapp
    assert "cap_drop:\n      - ALL" in miniapp
    assert "cap_add:\n      - NET_BIND_SERVICE" in miniapp
    assert "/tmp:size=16m,mode=1777" in miniapp
    assert "logging: *default-logging" in miniapp
    assert "http://127.0.0.1:2019/healthz" in miniapp
    assert "\n    env_file:" not in miniapp
    assert "BOT_TOKEN" not in miniapp
    assert "DATABASE_URL" not in miniapp
    assert "/var/run/docker.sock" not in COMPOSE
    assert "mem_limit" not in COMPOSE


def test_networks_keep_caddy_away_from_database() -> None:
    miniapp = service_block("miniapp")
    migrate = service_block("migrate")
    web = service_block("web")
    db = service_block("db")

    assert "\n      - edge" in miniapp
    assert "\n      - database" not in miniapp
    assert "\n      - database" in web
    assert "\n      - edge" in web
    assert "\n      - database" in migrate
    assert "\n      - edge" in migrate
    assert "\n      - database" in db
    assert "\n      - edge" not in db
    assert "database:\n    internal: true" in COMPOSE
