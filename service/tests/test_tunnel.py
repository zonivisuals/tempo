"""Brev port-forward supervisor (ADR-0008) against a fake CLI.

The fake `brev` listens on the requested local port like `brev port-forward`,
then exits after a short lifetime; the supervisor must report up, notice the
exit, and restart it.
"""

import socket
import sys
import time

from tempo_service.tunnel import Tunnel

FAKE_CLI = r'''
import socket, sys, time
port = int(sys.argv[sys.argv.index("--port") + 1].split(":")[0])
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", port)); srv.listen(8)
print("forwarding", port, flush=True)
time.sleep(float(sys.argv[1]))
'''


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait(predicate, timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_tunnel_reports_up_and_restarts_after_exit(tmp_path):
    script = tmp_path / "fake_brev.py"
    script.write_text(FAKE_CLI)
    exe = sys.executable.replace("\\", "/")
    port = _free_port()
    # argv after the CLI: port-forward <instance> --port L:R ; the fake reads its lifetime from argv[1].
    tunnel = Tunnel(f'"{exe}" "{script.as_posix()}" 1.5', "tempo-l4-instance", port, 8900,
                    backoff_min_s=0.1, backoff_max_s=0.2)
    assert tunnel.cmd[-4:] == ["port-forward", "tempo-l4-instance", "--port", f"{port}:8900"]
    tunnel.start()
    try:
        assert _wait(lambda: tunnel.state == "up")
        assert _wait(lambda: tunnel.spawns >= 2)  # exited after its lifetime, then restarted
        assert _wait(lambda: tunnel.state == "up")
    finally:
        tunnel.stop()
    assert tunnel.state == "off"


def test_missing_cli_is_down_not_a_crash():
    tunnel = Tunnel("definitely-not-a-brev-binary", "tempo-l4-instance", _free_port(), 8900,
                    backoff_min_s=0.05, backoff_max_s=0.1)
    tunnel.start()
    try:
        assert _wait(lambda: tunnel.state == "down")
        assert tunnel.spawns == 0
    finally:
        tunnel.stop()
