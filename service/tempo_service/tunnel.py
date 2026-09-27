"""Brev port-forward supervisor (ADR-0008).

Brev tunnels (secure links) require a browser login; the Brev console
reference directs API clients to `brev port-forward <instance> --port L:R`
(CLI connectivity docs: one mapping per command). The sidecar runs that
command as a child process, restarts it with capped exponential backoff
when it exits (instance stopped, network drop, laptop sleep), and reports
its state for /health:

  off      no Brev instance configured (direct TEMPO_BACKEND_URL)
  starting process running, local port not accepting yet
  up       process running and the local port accepts connections
  down     process exited; waiting to restart

The CLI command is config (`TEMPO_BREV_CLI`, `wsl brev` on Windows where the
CLI lives in WSL; WSL2 forwards its localhost ports to Windows).
"""

from __future__ import annotations

import logging
import shlex
import socket
import subprocess
import threading

log = logging.getLogger("tempo.tunnel")

PROBE_TIMEOUT_S = 0.5
CHECK_INTERVAL_S = 1.0
OUTPUT_LINE_MAX = 300


class Tunnel:
    def __init__(self, cli: str, instance: str, local_port: int, remote_port: int,
                 backoff_min_s: float, backoff_max_s: float) -> None:
        self.cmd = [*shlex.split(cli), "port-forward", instance, "--port", f"{local_port}:{remote_port}"]
        self.instance = instance
        self.local_port = local_port
        self.backoff_min_s = backoff_min_s
        self.backoff_max_s = backoff_max_s
        self._state = "starting"
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.spawns = 0

    @property
    def state(self) -> str:
        return self._state

    def _set(self, state: str) -> None:
        if state != self._state:
            log.info("tunnel %s: %s -> %s", self.instance, self._state, state)
            self._state = state

    def _port_open(self) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", self.local_port), timeout=PROBE_TIMEOUT_S):
                return True
        except OSError:
            return False

    def _pump(self, proc: subprocess.Popen) -> None:
        for line in iter(proc.stdout.readline, b""):  # type: ignore[union-attr]
            text = line.decode("utf-8", "replace").strip()
            if text:
                log.info("brev: %s", text[:OUTPUT_LINE_MAX])

    def _spawn(self) -> subprocess.Popen | None:
        try:
            proc = subprocess.Popen(
                self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            log.warning("tunnel %s: cannot run %r (%s)", self.instance, self.cmd[0], exc)
            return None
        self.spawns += 1
        threading.Thread(target=self._pump, args=(proc,), daemon=True, name="tempo-tunnel-output").start()
        return proc

    def _loop(self) -> None:
        backoff = self.backoff_min_s
        while not self._stop.is_set():
            self._set("starting")
            proc = self._proc = self._spawn()
            was_up = False
            while proc is not None and proc.poll() is None and not self._stop.is_set():
                if self._port_open():
                    was_up = True
                    backoff = self.backoff_min_s
                    self._set("up")
                self._stop.wait(CHECK_INTERVAL_S)
            if self._stop.is_set():
                break
            self._set("down")
            log.info("tunnel %s: exited (code %s), retry in %.0fs", self.instance,
                     proc.returncode if proc else "n/a", backoff)
            self._stop.wait(backoff)
            backoff = self.backoff_min_s if was_up else min(backoff * 2, self.backoff_max_s)

    def start(self) -> None:
        if self._thread is None:
            log.info("tunnel %s: %s", self.instance, " ".join(self.cmd))
            self._thread = threading.Thread(target=self._loop, daemon=True, name="tempo-tunnel")
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._set("off")
