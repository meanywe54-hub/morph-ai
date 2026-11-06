"""Opt-in integration tests. Run only on an isolated host with a trusted local image."""

import os

import pytest

from morph.sandbox import DockerSandbox, SandboxFailure

pytestmark = pytest.mark.skipif(
    os.environ.get("MORPH_DOCKER_TEST") != "1",
    reason="set MORPH_DOCKER_TEST=1 on an isolated Docker host",
)


@pytest.fixture
def sandbox():
    runner = DockerSandbox(
        image=os.environ.get("MORPH_DOCKER_IMAGE", "python:3.12-slim"), timeout=5
    )
    runner.preflight()
    return runner


def test_docker_executes_code_and_does_not_forward_host_environment(sandbox, monkeypatch):
    monkeypatch.setenv("MORPH_TEST_SENTINEL", "test-only")
    assert sandbox.run("def solve(values): return sum(values)", [4, -3]).answer == 1
    assert (
        sandbox.run(
            "import os\ndef solve(values): return int('MORPH_TEST_SENTINEL' in os.environ)", []
        ).answer
        == 0
    )


def test_docker_times_out_and_rejects_bad_return_type(sandbox):
    with pytest.raises(SandboxFailure):
        sandbox.run("def solve(values):\n while True: pass", [])
    with pytest.raises(SandboxFailure):
        sandbox.run("def solve(values): return 'not an integer'", [])
