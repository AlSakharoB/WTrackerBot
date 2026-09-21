#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
ruff_bin=${RUFF_BIN:-ruff}
pytest_bin=${PYTEST_BIN:-pytest}
staging_attested=${RELEASE_GATE_STAGING_ATTESTED:-false}
clients_attested=${RELEASE_GATE_CLIENTS_ATTESTED:-false}
critical_defects=${RELEASE_GATE_CRITICAL_HIGH_DEFECTS:-unknown}
ui_output=$(mktemp -d "${TMPDIR:-/tmp}/wtrackerbot-ui-audit.XXXXXX")

cleanup() {
    rm -rf "$ui_output"
}

fail() {
    echo "Release gate failed: $1" >&2
    exit 2
}

trap cleanup EXIT HUP INT TERM
cd "$project_dir"

for command in "$ruff_bin" "$pytest_bin" npm docker python3; do
    command -v "$command" >/dev/null 2>&1 || fail "$command is not installed"
done
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is unavailable"

echo "== Backend lint, format and unit tests =="
"$ruff_bin" check .
"$ruff_bin" format --check .
"$pytest_bin" tests/unit

echo "== Frontend clean install, tests, build and visual audit =="
(
    cd frontend
    npm ci
    npm run lint
    npm run typecheck
    npm test -- --run
    npm run build
    UI_AUDIT_OUTPUT="$ui_output" npm run audit:ui
)

echo "== Security gate =="
python3 scripts/miniapp_security_gate.py

echo "== Production Compose build =="
docker compose config --quiet
docker compose build

echo "== Backend migrations and full regression =="
./scripts/regression.sh

echo "Automated release gate passed."
case "$staging_attested:$clients_attested:$critical_defects" in
    true:true:0)
        echo "Staging, client matrix and defect attestations: passed."
        ;;
    *)
        cat >&2 <<'EOF'
Manual release evidence is incomplete. After the staging deployment regression,
Android/iOS/Desktop/Web checks and defect triage, rerun with:
  RELEASE_GATE_STAGING_ATTESTED=true \
  RELEASE_GATE_CLIENTS_ATTESTED=true \
  RELEASE_GATE_CRITICAL_HIGH_DEFECTS=0 \
  ./scripts/release_gate.sh
EOF
        exit 3
        ;;
esac

echo "Mini App release gate passed."
