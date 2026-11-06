from itertools import product

import pytest

from morph.bounded import BoundedRunner
from morph.sandbox import SandboxFailure


def test_interprets_new_loop_and_branch_algorithm():
    source = """def solve(values: list[int]) -> int:
    total = 0
    for value in values:
        if value < 0:
            total -= value
        else:
            total += value * 2
    return total
"""
    assert BoundedRunner().run(source, [3, -4, 2]).answer == 14
    assert BoundedRunner().run("def solve(values): return sum(values)", [5, -2]).answer == 3


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef solve(values): return 1",
        "def solve(values): return __import__('os').system('anything')",
        "def solve(values): return values.__class__",
        "def solve(values):\n while True: pass",
        "def solve(values): return open('anything')",
        "def solve(values): return [x for x in values]",
        "def solve(values): return solve(values)",
        "def solve(values): return 2 ** 1000000000",
        "def solve(values): return True",
        "def solve(values):\n if False:\n  import os\n return 1",
    ],
)
def test_rejects_unsupported_or_unsafe_constructs(source):
    with pytest.raises(SandboxFailure):
        BoundedRunner().run(source, [1])


def test_work_is_bounded_even_for_nested_finite_loops():
    source = """def solve(values):
    total = 0
    for x in values:
        for y in values:
            total += x * y
    return total
"""
    with pytest.raises(SandboxFailure, match="step"):
        BoundedRunner(max_steps=100).run(source, list(range(20)))


def test_integer_growth_and_input_size_are_bounded():
    with pytest.raises(SandboxFailure, match="integer"):
        BoundedRunner().run("def solve(values): return 1000000000 * 1000000000", [])
    with pytest.raises(SandboxFailure, match="input"):
        BoundedRunner().run("def solve(values): return 1", [0] * 1001)


def test_signed_arithmetic_matches_reference_over_small_domain():
    source = """def solve(values):
    total = 0
    for value in values:
        if value < 0:
            total += abs(value)
        else:
            total += value // 2
    return total
"""
    runner = BoundedRunner()
    for size in range(4):
        for values in product(range(-2, 3), repeat=size):
            expected = sum(abs(x) if x < 0 else x // 2 for x in values)
            assert runner.run(source, list(values)).answer == expected


def test_rejects_invalid_arithmetic_and_unbound_variables():
    for source in (
        "def solve(values): return 1 // 0",
        "def solve(values): return unknown",
        "def solve(values):\n for value in 1:\n  return value",
        "def solve(values): return min(values)",
    ):
        with pytest.raises(SandboxFailure):
            BoundedRunner().run(source, [])
