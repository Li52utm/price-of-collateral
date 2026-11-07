"""Shared test setup: no test may touch the network, and no test may modify the repository.

Every download path (requests, and any outbound socket) raises during tests, so a
test that tries to download fails loudly. Tests that need real data use the
committed snapshots in results/, which makes them deterministic and runnable offline.

Session guard: the git status (and a hash of every file it lists) is recorded when the session starts and
compared when it ends. If any tracked file was modified, deleted or created by the tests, the session FAILS and
the files are listed. Tests write only to temporary directories (tmp_path); rebuilds use
`run_all.py --out-dir` (tests/test_determinism.py).
"""

from __future__ import annotations

import hashlib
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NUL = "\x00"   # git status -z separates entries with NUL bytes
_START: dict[str, str] | None = None


def repo_state(root: Path = ROOT) -> dict[str, str] | None:
    """{path: status + content hash} for every changed or untracked (not ignored) file; None outside git."""
    try:
        out = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=root,
                             capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    state = {}
    for entry in filter(None, out.stdout.decode("utf-8").split(NUL)):
        status, path = entry[:2], entry[3:]
        f = root / path
        digest = hashlib.sha256(f.read_bytes()).hexdigest() if f.is_file() else "missing"
        state[path] = f"{status} {digest}"
    return state


def changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Paths whose status or content differs between two repo states."""
    return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))


def pytest_sessionstart(session: pytest.Session) -> None:
    global _START
    _START = repo_state()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _START is None:
        return
    after = repo_state()
    changed = changed_files(_START, after) if after is not None else []
    if changed:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        msg = ("FAILED: the tests modified files in the repository (tests must write only to tmp_path):\n   "
               + "\n   ".join(changed))
        if reporter is not None:
            reporter.write_line(msg, red=True, bold=True)
        else:
            print(msg)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


class NetworkBlocked(RuntimeError):
    """Raised when a test tries to download something."""


def _blocked(*args, **kwargs):
    raise NetworkBlocked("tests must not use the network: use the committed snapshots in results/")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    monkeypatch.setattr(requests.Session, "request", _blocked)
    monkeypatch.setattr(requests, "get", _blocked)
    real_connect = socket.socket.connect

    def local_only(sock, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "localhost", "::1"):
            _blocked()
        return real_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", local_only)
