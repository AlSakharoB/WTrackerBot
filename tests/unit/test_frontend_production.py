from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"


def test_frontend_image_runs_quality_gate_and_contains_only_static_runtime() -> None:
    dockerfile = (FRONTEND_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM ${NODE_IMAGE} AS dependencies" in dockerfile
    assert "RUN npm ci" in dockerfile
    assert "npm run lint" in dockerfile
    assert "npm run typecheck" in dockerfile
    assert "npm test" in dockerfile
    assert "npm run build" in dockerfile
    assert "npm run verify:build" in dockerfile
    assert "FROM ${CADDY_IMAGE} AS runtime" in dockerfile
    assert "COPY --from=build /app/dist /srv" in dockerfile
    assert "COPY --from=build /app/node_modules" not in dockerfile


def test_frontend_build_context_excludes_local_and_sensitive_files() -> None:
    ignored = set(
        (FRONTEND_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    )

    assert {
        ".env",
        ".env.*",
        "node_modules/",
        "dist/",
        "coverage/",
        "screenshots/",
        "playwright-report/",
        "test-results/",
        "design/",
    } <= ignored


def test_caddy_routes_api_and_spa_without_exposing_internal_health() -> None:
    caddyfile = (FRONTEND_ROOT / "Caddyfile").read_text(encoding="utf-8")

    assert "{$MINIAPP_DOMAIN:localhost}" in caddyfile
    assert "@internal path /internal /internal/*" in caddyfile
    assert "respond 404" in caddyfile
    assert "@api path /api /api/*" in caddyfile
    assert "reverse_proxy web:{$MINIAPP_PORT:8080}" in caddyfile
    assert "health_uri /internal/readyz" in caddyfile
    assert "try_files {path} /index.html" in caddyfile
    assert "root * /srv" in caddyfile
    assert "http://127.0.0.1:2019" in caddyfile
    assert 'respond "ok" 200' in caddyfile


def test_caddy_security_and_cache_contract_is_telegram_compatible() -> None:
    caddyfile = (FRONTEND_ROOT / "Caddyfile").read_text(encoding="utf-8")

    assert "Strict-Transport-Security" in caddyfile
    assert 'X-Content-Type-Options "nosniff"' in caddyfile
    assert 'Referrer-Policy "no-referrer"' in caddyfile
    assert (
        'Permissions-Policy "camera=(self), microphone=(), geolocation=()"' in caddyfile
    )
    assert "script-src 'self' https://telegram.org" in caddyfile
    assert "connect-src 'self'" in caddyfile
    assert "object-src 'none'" in caddyfile
    assert "unsafe-eval" not in caddyfile
    assert "X-Frame-Options" not in caddyfile
    assert "\n\tlog " not in caddyfile
    assert 'Cache-Control "public, max-age=31536000, immutable"' in caddyfile
    assert 'Cache-Control "no-cache, no-store, must-revalidate"' in caddyfile


def test_vite_explicitly_disables_source_maps() -> None:
    vite_config = (FRONTEND_ROOT / "vite.config.ts").read_text(encoding="utf-8")

    assert "sourcemap: false" in vite_config
