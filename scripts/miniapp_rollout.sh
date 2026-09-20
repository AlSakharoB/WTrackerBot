#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
env_file=${ENV_FILE:-$project_dir/.env}
command=${1:-status}
required_stage=${2:-}

fail() {
    echo "Mini App rollout check failed: $1" >&2
    exit 2
}

setting_value() {
    awk -F= -v expected="$1" '
        $1 == expected {
            sub(/^[^=]*=/, "")
            print
            found = 1
        }
        END { if (!found) exit 1 }
    ' "$env_file"
}

show_checklist() {
    cat <<'EOF'
Production admin checklist:
1. Open ration, food, weight and profile sections.
2. Create, edit and delete an ingredient.
3. Check barcode lookup and image fallback.
4. Create and edit a dish.
5. Add the dish to the ration.
6. Check macros with and without goals.
7. Add weight; check pan, pinch and reset.
8. Change profile settings and a reminder.
9. Open a sharing preview.
10. Verify the same data in the regular bot UI.
11. Check light/dark themes and reopen the Mini App.
EOF
}

[ -f "$env_file" ] || fail "environment file is missing"

case "$command" in
    checklist)
        show_checklist
        exit 0
        ;;
    status | require) ;;
    *) fail "usage: miniapp_rollout.sh [status|checklist|require STAGE]" ;;
esac

enabled=$(setting_value MINIAPP_ENABLED) || fail "MINIAPP_ENABLED is missing"
allowed_ids=$(setting_value MINIAPP_ALLOWED_TELEGRAM_IDS) || \
    fail "MINIAPP_ALLOWED_TELEGRAM_IDS is missing"
manage_button=$(setting_value MINIAPP_MANAGE_MENU_BUTTON) || \
    fail "MINIAPP_MANAGE_MENU_BUTTON is missing"

case "$enabled:$manage_button" in
    false:true | false:false) stage=disabled ;;
    true:true)
        if [ -n "$allowed_ids" ]; then
            stage=limited
        else
            stage=global
        fi
        ;;
    true:false) stage=external-management ;;
    *) fail "feature flag values must be true or false" ;;
esac

if [ -n "$allowed_ids" ]; then
    allowlist_count=$(printf '%s\n' "$allowed_ids" | awk -F, '{ print NF }')
else
    allowlist_count=0
fi
echo "Mini App rollout stage: $stage (allowlist entries: $allowlist_count)"

if [ "$command" = "require" ]; then
    case "$required_stage" in
        disabled | limited | global) ;;
        *) fail "required stage must be disabled, limited or global" ;;
    esac
    [ "$stage" = "$required_stage" ] || \
        fail "expected $required_stage stage, current stage is $stage"
fi
