"""Explicit selection of a recorded patch runtime."""

from morph.bounded import BoundedRunner
from morph.sandbox import DockerSandbox


def runner_for(runtime: str, image: str = "python:3.12-slim") -> BoundedRunner | DockerSandbox:
    if runtime == "bounded-integer-v1":
        return BoundedRunner()
    if runtime == "docker-python":
        return DockerSandbox(image=image)
    raise ValueError("unsupported patch runtime")
