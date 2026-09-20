import fcntl
import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
DEPLOY_SCRIPT = PROJECT_ROOT / "scripts/deploy.sh"
ROLLBACK_SCRIPT = PROJECT_ROOT / "scripts/rollback.sh"
FAKE_DEPLOY_CLI = PROJECT_ROOT / "tests/fixtures/fake_deploy_cli.sh"


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def prepare_deploy(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "BOT_TOKEN=test-secret-token",
                "POSTGRES_PASSWORD=test-secret-password",
                "DATABASE_URL=postgresql+asyncpg://postgres:test@db/nutrition_bot",
                "APP_ENVIRONMENT=production",
                "APP_VERSION=1.0.3",
                "MINIAPP_ENABLED=false",
                "MINIAPP_DOMAIN=app.test",
                "MINIAPP_ACME_EMAIL=admin@app.test",
                "MINIAPP_EXPECTED_IPV4=203.0.113.10",
                "MINIAPP_EXPECTED_IPV6=",
                "MINIAPP_SSH_PORT=22",
                "MINIAPP_PUBLIC_URL=https://app.test",
                "MINIAPP_CORS_ORIGINS=https://app.test",
                "MINIAPP_ALLOWED_TELEGRAM_IDS=",
                "MINIAPP_MANAGE_MENU_BUTTON=true",
                "MINIAPP_MENU_BUTTON_TEXT=Open diary",
                "",
            ]
        ),
        encoding="utf-8",
    )
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_log = tmp_path / "docker.log"
    curl_log = tmp_path / "curl.log"

    for command in ("docker", "curl", "git"):
        bin_dir.joinpath(command).symlink_to(FAKE_DEPLOY_CLI)

    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:{environment['PATH']}",
            "COMPOSE_FILE": str(compose_file),
            "ENV_FILE": str(env_file),
            "ENV_EXAMPLE_FILE": str(env_file),
            "DEPLOY_ALLOW_DIRTY_SOURCE": "true",
            "DEPLOY_LOCK_FILE": str(tmp_path / "deploy.lock"),
            "MINIAPP_PREFLIGHT_SKIP_SYSTEM_CHECKS": "true",
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_CURL_LOG": str(curl_log),
        }
    )
    return environment, docker_log, curl_log


def run_deploy(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(DEPLOY_SCRIPT)],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_deploy_runs_smoke_before_cleanup_and_records_revision(tmp_path: Path) -> None:
    environment, docker_log, curl_log = prepare_deploy(tmp_path)

    result = run_deploy(environment)

    assert result.returncode == 0, result.stdout + result.stderr
    calls = docker_log.read_text(encoding="utf-8")
    assert calls.index("build backup bot miniapp") < calls.index(
        "up -d --no-build --wait"
    )
    assert calls.index("exec -T bot") < calls.index("exec -T web")
    assert calls.index("exec -T web") < calls.index("exec -T miniapp")
    assert calls.index("exec -T miniapp") < calls.index("image prune -a -f")
    assert calls.index("image prune -a -f") < calls.index("builder prune -a -f")
    assert "rm -f backup migrate" in calls
    assert "--volumes" not in calls
    assert "Deploy completed: APP_VERSION=1.0.3 GIT_COMMIT_SHA=" in result.stdout
    curl_calls = curl_log.read_text(encoding="utf-8")
    assert "https://app.test/" in curl_calls
    assert "https://app.test/api/v1/me" in curl_calls
    assert "https://app.test/internal/readyz" in curl_calls
    assert "test-secret" not in result.stdout + result.stderr


def test_failed_healthcheck_prints_logs_without_cleanup(tmp_path: Path) -> None:
    environment, docker_log, _curl_log = prepare_deploy(tmp_path)
    environment["FAKE_DOCKER_FAIL_MATCH"] = "exec -T web"

    result = run_deploy(environment)

    assert result.returncode == 42
    calls = docker_log.read_text(encoding="utf-8")
    assert "logs --no-color --tail=200 db backup migrate bot web miniapp" in calls
    assert "image prune" not in calls
    assert "builder prune" not in calls
    assert "rm -f backup migrate" not in calls
    assert "cleanup was not started" in result.stderr
    assert "Deploy completed" not in result.stdout


def test_failed_frontend_healthcheck_does_not_start_cleanup(tmp_path: Path) -> None:
    environment, docker_log, _curl_log = prepare_deploy(tmp_path)
    environment["FAKE_DOCKER_FAIL_MATCH"] = "exec -T miniapp"

    result = run_deploy(environment)

    assert result.returncode == 42
    calls = docker_log.read_text(encoding="utf-8")
    assert "logs --no-color --tail=200 db backup migrate bot web miniapp" in calls
    assert "image prune" not in calls
    assert "builder prune" not in calls
    assert "rm -f backup migrate" not in calls
    assert "Deploy completed" not in result.stdout


def test_deploy_can_repeat_the_same_revision(tmp_path: Path) -> None:
    environment, docker_log, _curl_log = prepare_deploy(tmp_path)

    first = run_deploy(environment)
    second = run_deploy(environment)

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    calls = docker_log.read_text(encoding="utf-8")
    assert calls.count("build backup bot miniapp") == 2
    assert calls.count("up -d --no-build --wait") == 2
    assert calls.count("image prune -a -f") == 2


def test_deploy_lock_rejects_parallel_run(tmp_path: Path) -> None:
    environment, docker_log, _curl_log = prepare_deploy(tmp_path)
    lock_path = Path(environment["DEPLOY_LOCK_FILE"])

    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run_deploy(environment)

    assert result.returncode == 2
    assert "another deploy or rollback is already running" in result.stderr
    assert not docker_log.exists()


def test_deploy_rejects_missing_inherited_lock(tmp_path: Path) -> None:
    environment, docker_log, _curl_log = prepare_deploy(tmp_path)
    environment["DEPLOY_LOCK_HELD"] = "true"

    result = run_deploy(environment)

    assert result.returncode == 2
    assert "inherited deploy lock is unavailable" in result.stderr
    assert not docker_log.exists()


def test_rollback_uses_detached_worktree_and_never_downgrades_database() -> None:
    rollback = ROLLBACK_SCRIPT.read_text(encoding="utf-8")

    assert "worktree add --detach" in rollback
    assert "merge-base --is-ancestor" in rollback
    assert "sha256sum" in rollback
    assert "/backups/.last-verified" in rollback
    assert "verify_database_revision" in rollback
    assert "DEPLOY_SKIP_BUILD=true" in rollback
    assert "DEPLOY_LOCK_HELD=true" in rollback
    assert "reset --hard" not in rollback
    assert "alembic downgrade" not in rollback.lower()
    assert "down -v" not in rollback


def test_rollback_runs_from_tag_without_changing_main_checkout(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is not installed in the test image")

    project = tmp_path / "project"
    scripts = project / "scripts"
    frontend = project / "frontend"
    scripts.mkdir(parents=True)
    frontend.mkdir()
    shutil.copy2(ROLLBACK_SCRIPT, scripts / "rollback.sh")
    write_executable(
        scripts / "deploy.sh",
        """#!/bin/sh
printf '%s|%s|%s|%s\n' \
    "$DEPLOY_APP_VERSION" "$DEPLOY_SKIP_BUILD" \
    "$DEPLOY_LOCK_HELD" "$ENV_FILE" >"$FAKE_DEPLOY_LOG"
""",
    )
    (project / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (project / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (frontend / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (frontend / "Caddyfile").write_text(":80 { respond 200 }\n", encoding="utf-8")
    (project / ".gitignore").write_text(".env\n", encoding="utf-8")
    env_file = project / ".env"
    env_file.write_text("APP_VERSION=1.0.1\n", encoding="utf-8")

    subprocess.run(["git", "init", "-q", project], check=True)
    subprocess.run(
        ["git", "-C", project, "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", project, "config", "user.name", "Test User"], check=True
    )
    subprocess.run(["git", "-C", project, "add", "."], check=True)
    subprocess.run(["git", "-C", project, "commit", "-qm", "old release"], check=True)
    subprocess.run(["git", "-C", project, "tag", "v1.0.0"], check=True)
    (project / "release.txt").write_text("current\n", encoding="utf-8")
    subprocess.run(["git", "-C", project, "add", "release.txt"], check=True)
    subprocess.run(
        ["git", "-C", project, "commit", "-qm", "current release"], check=True
    )
    current_head = subprocess.run(
        ["git", "-C", project, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    bin_dir = tmp_path / "rollback-bin"
    bin_dir.mkdir()
    docker_log = tmp_path / "rollback-docker.log"
    deploy_log = tmp_path / "rollback-deploy.log"
    write_executable(
        bin_dir / "docker",
        """#!/bin/sh
printf '%s\n' "$*" >>"$FAKE_DOCKER_LOG"
case "$*" in
    *" ps -q db") printf 'test-db-container\n' ;;
    *"Config.Labels"*) printf 'test-project\n' ;;
    *"inspect --format {{.Image}}"*) printf 'sha256:test-db-image\n' ;;
    *"volume ls"*) printf 'test-project_postgres_backups\n' ;;
esac
exit 0
""",
    )
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:{environment['PATH']}",
            "DEPLOY_LOCK_FILE": str(tmp_path / "rollback.lock"),
            "FAKE_DOCKER_LOG": str(docker_log),
            "FAKE_DEPLOY_LOG": str(deploy_log),
        }
    )

    result = subprocess.run(
        [str(scripts / "rollback.sh"), "v1.0.0"],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Rollback completed: v1.0.0" in result.stdout
    assert env_file.read_text(encoding="utf-8") == "APP_VERSION=1.0.1\n"
    assert (
        subprocess.run(
            ["git", "-C", project, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        == current_head
    )
    assert (
        len(
            subprocess.run(
                ["git", "-C", project, "worktree", "list", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.split("worktree ")
        )
        == 2
    )
    assert deploy_log.read_text(encoding="utf-8") == (f"1.0.0|true|true|{env_file}\n")
    calls = docker_log.read_text(encoding="utf-8")
    assert calls.index("exec -T web") < calls.index("sha256sum")
    assert calls.index("build backup bot miniapp") < calls.index(
        "verify_database_revision"
    )


def test_application_image_does_not_require_ignored_readme() -> None:
    dockerfile = PROJECT_ROOT.joinpath("Dockerfile").read_text(encoding="utf-8")
    package = PROJECT_ROOT.joinpath("pyproject.toml").read_text(encoding="utf-8")

    assert "COPY pyproject.toml ./" in dockerfile
    assert "COPY pyproject.toml README.md" not in dockerfile
    assert (
        'readme = { text = "Telegram bot for tracking nutrition and weight."' in package
    )
