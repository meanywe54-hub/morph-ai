"""Experimental container runner. A container is not a hardened VM boundary."""

import json
import re
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass


class SandboxUnavailable(RuntimeError):
    """The required isolation infrastructure could not be used."""


class SandboxFailure(RuntimeError):
    """The candidate did not produce a valid result."""


@dataclass(frozen=True)
class SandboxResult:
    answer: int


_HARNESS = """\
import json, sys
p = json.load(sys.stdin)
namespace = {}
exec(compile(p['code'], '<candidate>', 'exec'), namespace)
answer = namespace['solve'](p['values'])
if type(answer) is not int:
    raise TypeError('solve must return an integer')
print(json.dumps({'answer': answer}))
"""


class DockerSandbox:
    """Execute a candidate against public input in a locally available trusted image.

    Docker's daemon and image must be trusted; do not treat this as a multi-tenant sandbox.
    """

    runtime = "docker-python"

    def __init__(self, image: str = "python:3.12-slim", timeout: float = 10.0):
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/:@-]{0,250}", image):
            raise ValueError("invalid image reference")
        if not 0 < timeout <= 60:
            raise ValueError("timeout must be in (0, 60]")
        self.image = image
        self.timeout = timeout

    def preflight(self) -> None:
        docker = shutil.which("docker")
        if not docker:
            raise SandboxUnavailable("Docker is required; host execution is disabled")
        try:
            for command in ([docker, "info"], [docker, "image", "inspect", self.image]):
                result = subprocess.run(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=False,
                )
                if result.returncode:
                    raise SandboxUnavailable("Docker daemon or local image is unavailable")
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SandboxUnavailable("Docker preflight failed") from exc

    def run(self, code: str, values: list[int]) -> SandboxResult:
        if len(code.encode("utf-8")) > 100_000:
            raise ValueError("candidate too large")
        if len(values) > 1000 or any(type(v) is not int or abs(v) > 10**9 for v in values):
            raise ValueError("invalid input")
        docker = shutil.which("docker")
        if not docker:
            raise SandboxUnavailable("Docker is required; host execution is disabled")
        name = "morph-" + uuid.uuid4().hex
        cmd = [
            docker,
            "run",
            "--rm",
            "--interactive",
            "--name",
            name,
            "--pull",
            "never",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "32",
            "--memory",
            "128m",
            "--memory-swap",
            "128m",
            "--cpus",
            "0.5",
            "--user",
            "65534:65534",
            "--log-driver",
            "none",
            "--entrypoint",
            "python",
            self.image,
            "-I",
            "-c",
            _HARNESS,
        ]
        try:
            process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except OSError as exc:
            raise SandboxUnavailable("could not start Docker") from exc
        output: list[bytes] = []
        overflow = threading.Event()

        def drain(stream, target):
            retained = 0
            while chunk := stream.read(4096):
                retained += len(chunk)
                if retained > 65536:
                    overflow.set()
                    process.kill()
                    break
                target.append(chunk)

        errors: list[bytes] = []

        def send_input():
            try:
                assert process.stdin is not None
                process.stdin.write(json.dumps({"code": code, "values": values}).encode())
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        threads = [
            threading.Thread(target=drain, args=(process.stdout, output), daemon=True),
            threading.Thread(target=drain, args=(process.stderr, errors), daemon=True),
            threading.Thread(target=send_input, daemon=True),
        ]
        for thread in threads:
            thread.start()
        try:
            process.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait()
            raise SandboxFailure("container timed out or closed input") from exc
        finally:
            # Killing the CLI alone does not guarantee the container stops.
            try:
                subprocess.run(
                    [docker, "rm", "-f", name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
            for thread in threads:
                thread.join(timeout=2)
        if overflow.is_set():
            raise SandboxFailure("container output limit exceeded")
        if process.returncode != 0:
            raise SandboxFailure("container failed or image is unavailable")
        try:
            result = json.loads(b"".join(output))
            answer = result["answer"]
            if type(answer) is not int:
                raise ValueError("answer must be an integer")
        except (ValueError, KeyError, TypeError) as exc:
            raise SandboxFailure("invalid candidate output") from exc
        return SandboxResult(answer)
