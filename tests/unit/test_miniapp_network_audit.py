import socket
import subprocess
from pathlib import Path
from unittest.mock import Mock

from scripts.miniapp_external_ports import (
    DEFAULT_CLOSED_PORTS,
    audit_tcp_ports,
    main,
)

PROJECT_ROOT = Path(__file__).parents[2]
HOST_AUDIT = PROJECT_ROOT / "scripts/miniapp_host_audit.sh"
PUBLIC_AUDIT = PROJECT_ROOT / "scripts/miniapp_public_audit.sh"


def connector_for(open_ports: set[int]):
    def connect(address: tuple[str, int], timeout: float) -> socket.socket:
        assert address[0] == "203.0.113.10"
        assert timeout == 0.25
        if address[1] not in open_ports:
            raise OSError("connection refused")
        return Mock(spec=socket.socket)

    return connect


def test_external_port_audit_accepts_expected_public_surface() -> None:
    results = audit_tcp_ports(
        "203.0.113.10",
        open_ports=(2222, 80, 443),
        closed_ports=DEFAULT_CLOSED_PORTS,
        timeout_seconds=0.25,
        connector=connector_for({2222, 80, 443}),
    )

    assert all(result.passed for result in results)
    assert {result.port for result in results if result.actual_open} == {
        2222,
        80,
        443,
    }


def test_external_port_audit_detects_closed_ssh_and_public_database() -> None:
    results = audit_tcp_ports(
        "203.0.113.10",
        open_ports=(22, 80, 443),
        closed_ports=DEFAULT_CLOSED_PORTS,
        timeout_seconds=0.25,
        connector=connector_for({80, 443, 5432}),
    )

    failures = {result.port for result in results if not result.passed}
    assert failures == {22, 5432}


def test_external_port_cli_returns_nonzero_for_policy_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.miniapp_external_ports.socket.create_connection",
        connector_for({80, 443, 8080}),
    )

    assert (
        main(
            [
                "--host",
                "203.0.113.10",
                "--ssh-port",
                "2222",
                "--timeout",
                "0.25",
            ]
        )
        == 2
    )


def test_network_audit_shell_scripts_are_valid_and_read_only() -> None:
    for script in (HOST_AUDIT, PUBLIC_AUDIT):
        result = subprocess.run(
            ["sh", "-n", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    host_script = HOST_AUDIT.read_text(encoding="utf-8")
    public_script = PUBLIC_AUDIT.read_text(encoding="utf-8")
    assert "timedatectl show --property=NTPSynchronized" in host_script
    assert "5432 8080 5173 5174" in host_script
    assert "docker compose" in host_script
    assert "restart miniapp" in host_script
    assert "dig +short" in public_script
    assert "-verify_hostname" in public_script
    assert "-verify_return_error" in public_script
    assert "-checkend" in public_script
    assert "miniapp_external_ports.py" in public_script
    for destructive_command in (
        "ufw enable",
        "iptables -",
        "nft add",
        "docker volume prune",
        "down -v",
    ):
        assert destructive_command not in host_script + public_script


def test_deploy_runs_host_audit_before_cleanup() -> None:
    deploy = PROJECT_ROOT.joinpath("scripts/deploy.sh").read_text(encoding="utf-8")

    assert deploy.index("miniapp_host_audit.sh") < deploy.index("Smoke tests passed")
    assert deploy.index("miniapp_host_audit.sh") < deploy.index("docker image prune")


def test_public_audit_template_does_not_contain_secrets() -> None:
    template = PROJECT_ROOT.joinpath("scripts/miniapp-audit.env.example").read_text(
        encoding="utf-8"
    )

    assert "MINIAPP_EXPECTED_IPV4=" in template
    assert "MINIAPP_EXPECTED_IPV6=" in template
    assert "MINIAPP_SSH_PORT=22" in template
    assert "BOT_TOKEN" not in template
    assert "PASSWORD" not in template
