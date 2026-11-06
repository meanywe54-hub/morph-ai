import io
import subprocess

import pytest

from morph.sandbox import DockerSandbox, SandboxFailure, SandboxUnavailable


def test_missing_docker_fails_closed(monkeypatch):
    monkeypatch.setattr("morph.sandbox.shutil.which", lambda _: None)
    with pytest.raises(SandboxUnavailable):
        DockerSandbox().run("def solve(values): return sum(values)", [1, 2])


def test_rejects_oversized_code_before_invoking_docker(monkeypatch):
    monkeypatch.setattr("morph.sandbox.shutil.which", lambda _: pytest.fail("invoked docker"))
    with pytest.raises(ValueError):
        DockerSandbox().run("x" * 100_001, [1])


def test_docker_command_requests_isolation_and_cleanup(monkeypatch):
    commands = []

    class Process:
        def __init__(self, command, **kwargs):
            commands.append(command)
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO(b'{"answer": 3}')
            self.stderr = io.BytesIO()
            self.returncode = 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("morph.sandbox.shutil.which", lambda _: "docker")
    monkeypatch.setattr("morph.sandbox.subprocess.Popen", Process)
    monkeypatch.setattr(
        "morph.sandbox.subprocess.run", lambda command, **kw: commands.append(command)
    )
    assert DockerSandbox().run("def solve(values): return 3", []).answer == 3
    cmd = commands[0]
    assert cmd[cmd.index("--network") + 1] == "none"
    assert cmd[cmd.index("--pull") + 1] == "never"
    assert "--read-only" in cmd and "--cap-drop" in cmd and "--pids-limit" in cmd
    assert "--memory" in cmd and "--cpus" in cmd and "--user" in cmd
    assert commands[-1][1:3] == ["rm", "-f"]


def test_timeout_attempts_container_cleanup(monkeypatch):
    commands = []

    class Process:
        def __init__(self, command, **kwargs):
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO()
            self.killed = False

        def wait(self, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired("docker", timeout)
            return 0

        def kill(self):
            self.killed = True

    monkeypatch.setattr("morph.sandbox.shutil.which", lambda _: "docker")
    monkeypatch.setattr("morph.sandbox.subprocess.Popen", Process)
    monkeypatch.setattr(
        "morph.sandbox.subprocess.run", lambda command, **kw: commands.append(command)
    )
    with pytest.raises(SandboxFailure, match="timed out"):
        DockerSandbox().run("def solve(values): pass", [])
    assert commands[-1][1:3] == ["rm", "-f"]
