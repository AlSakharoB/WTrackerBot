import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]


class SecurityGateError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SecurityGateError(message)


def read(relative_path: str) -> str:
    return PROJECT_ROOT.joinpath(relative_path).read_text(encoding="utf-8")


def service_block(compose: str, name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-z][a-z0-9_-]*:\n|^volumes:|\Z)",
        compose,
        flags=re.MULTILINE | re.DOTALL,
    )
    require(match is not None, f"Compose service is missing: {name}")
    return match.group("body")  # type: ignore[union-attr]


def configured_secrets() -> tuple[bytes, ...]:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        return ()
    secret_keys = {"BOT_TOKEN", "POSTGRES_PASSWORD", "DATABASE_URL"}
    secrets: list[bytes] = []
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in secret_keys and len(value) >= 8:
            secrets.append(value.encode())
    return tuple(secrets)


def check_frontend_bundle() -> None:
    dist = PROJECT_ROOT / "frontend/dist"
    require(dist.is_dir(), "frontend/dist is missing; run npm run build first")
    forbidden_markers = (
        b"BOT_TOKEN=",
        b"POSTGRES_PASSWORD=",
        b"postgresql+asyncpg://",
        *configured_secrets(),
    )
    files = [path for path in dist.rglob("*") if path.is_file()]
    require(files, "frontend/dist is empty")
    require(not any(path.suffix == ".map" for path in files), "source map found")
    for path in files:
        content = path.read_bytes()
        require(
            not any(marker and marker in content for marker in forbidden_markers),
            f"secret-like value found in frontend bundle: {path.name}",
        )


def run_security_gate(*, check_bundle: bool = True) -> tuple[str, ...]:
    compose = read("docker-compose.yml")
    caddy = read("frontend/Caddyfile")
    dockerignore = read(".dockerignore")
    frontend_ignore = read("frontend/.dockerignore")
    frontend_client = read("frontend/src/api/client.ts")
    scanner = read("frontend/src/components/food/BarcodeScannerSheet.tsx")
    web_auth = read("app/web/auth.py")
    web_dependencies = read("app/web/dependencies.py")
    web_app = read("app/web/app.py")
    web_main = read("app/web/main.py")
    preflight = read("scripts/miniapp_preflight.sh")

    require("hmac.compare_digest" in web_auth, "initData signature check is missing")
    require("auth_date" in web_auth, "initData age check is missing")
    require(
        "settings.miniapp_enabled" in web_dependencies
        and "miniapp_allowed_telegram_ids" in web_dependencies,
        "server-side feature flag or allowlist is missing",
    )
    require(
        "Production MINIAPP_PUBLIC_URL must use HTTPS" in read("app/config.py"),
        "production HTTPS validation is missing",
    )
    require(
        "MINIAPP_CORS_ORIGINS must exactly match" in preflight
        and "allow_origins=list(resolved_settings.miniapp_cors_origins)" in web_app,
        "exact production CORS validation is missing",
    )
    require("unsafe-eval" not in caddy, "CSP permits unsafe-eval")
    require("@internal path /internal /internal/*" in caddy, "internal routes leak")
    require("respond 404" in caddy, "internal routes are not denied")
    require("access_log=False" in web_main, "Web API access logging is enabled")
    require("\n\tlog " not in caddy, "Caddy access logging is enabled")

    miniapp = service_block(compose, "miniapp")
    database = service_block(compose, "db")
    require('"127.0.0.1:${POSTGRES_PORT:-5432}:5432"' in database, "DB is public")
    for service in ("backup", "migrate", "bot", "web"):
        require(
            "\n    ports:" not in service_block(compose, service),
            f"{service} publishes ports",
        )
    require('"80:80"' in miniapp and '"443:443"' in miniapp, "HTTPS edge is missing")
    require("/var/run/docker.sock" not in compose, "Docker socket is mounted")
    require("privileged:" not in compose, "privileged container is configured")
    require("cap_drop:\n      - ALL" in miniapp, "Caddy capabilities are not dropped")
    require(
        "cap_add:\n      - NET_BIND_SERVICE" in miniapp, "unexpected Caddy capability"
    )

    for ignored in (dockerignore, frontend_ignore):
        require(".env" in ignored, "Docker context does not exclude .env")
    require("COPY .env" not in read("Dockerfile"), "backend image copies .env")
    require(
        "COPY .env" not in read("frontend/Dockerfile"), "frontend image copies .env"
    )
    middleware = read("app/web/middleware.py")
    require(
        "Authorization" not in middleware and "initData" not in middleware,
        "authentication data is referenced by request logging",
    )

    literal_fetches = re.findall(r'fetch\([`"]([^`"]+)', frontend_client)
    require(literal_fetches, "frontend API calls were not found")
    require(
        all(target.startswith("/api/") for target in literal_fetches),
        "frontend performs a direct external fetch",
    )
    require(
        "world.openfoodfacts.org/api" not in frontend_client,
        "frontend calls Open Food Facts directly",
    )
    require(
        "onClick={() => void startCamera()}" in scanner
        and "decodeFromConstraints" in scanner,
        "camera is not gated by an explicit user action",
    )

    if check_bundle:
        check_frontend_bundle()
    return (
        "Telegram auth, feature flag and allowlist",
        "HTTPS, exact CORS and CSP",
        "private API/DB/internal routes",
        "container privileges and Docker contexts",
        "frontend bundle secrets and source maps",
        "camera user action and backend-only OFF lookup",
        "request-header and access-log privacy",
    )


def main() -> int:
    try:
        checks = run_security_gate()
    except (OSError, SecurityGateError) as error:
        print(f"Mini App security gate failed: {error}", file=sys.stderr)
        return 2
    for check in checks:
        print(f"PASS: {check}")
    print("Mini App security gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
