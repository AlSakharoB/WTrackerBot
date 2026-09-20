from __future__ import annotations

import argparse
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass

DEFAULT_CLOSED_PORTS = (5432, 8080, 5173, 5174)
Connector = Callable[[tuple[str, int], float], socket.socket]


@dataclass(frozen=True, slots=True)
class PortAudit:
    port: int
    expected_open: bool
    actual_open: bool

    @property
    def passed(self) -> bool:
        return self.expected_open == self.actual_open


def probe_tcp_port(
    host: str,
    port: int,
    *,
    timeout_seconds: float,
    connector: Connector | None = None,
) -> bool:
    resolved_connector = connector or socket.create_connection
    try:
        connection = resolved_connector((host, port), timeout_seconds)
    except OSError:
        return False
    connection.close()
    return True


def audit_tcp_ports(
    host: str,
    *,
    open_ports: Sequence[int],
    closed_ports: Sequence[int],
    timeout_seconds: float,
    connector: Connector | None = None,
) -> list[PortAudit]:
    results = [
        PortAudit(
            port=port,
            expected_open=True,
            actual_open=probe_tcp_port(
                host,
                port,
                timeout_seconds=timeout_seconds,
                connector=connector,
            ),
        )
        for port in open_ports
    ]
    results.extend(
        PortAudit(
            port=port,
            expected_open=False,
            actual_open=probe_tcp_port(
                host,
                port,
                timeout_seconds=timeout_seconds,
                connector=connector,
            ),
        )
        for port in closed_ports
    )
    return results


def _port(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= 65_535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check Mini App ports from a machine outside the server.",
    )
    parser.add_argument("--host", required=True, help="Production server address")
    parser.add_argument("--ssh-port", type=_port, default=22)
    parser.add_argument("--timeout", type=float, default=3.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = audit_tcp_ports(
        args.host,
        open_ports=(args.ssh_port, 80, 443),
        closed_ports=DEFAULT_CLOSED_PORTS,
        timeout_seconds=args.timeout,
    )
    for result in results:
        expectation = "open" if result.expected_open else "closed"
        actual = "open" if result.actual_open else "closed"
        marker = "PASS" if result.passed else "FAIL"
        print(f"{marker} tcp/{result.port}: expected {expectation}, found {actual}")
    return 0 if all(result.passed for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
