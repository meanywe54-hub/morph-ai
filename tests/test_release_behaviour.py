import json
from types import SimpleNamespace

import pytest

from morph.cli import main


def test_invalid_model_candidate_is_a_concise_cli_error(monkeypatch, capsys):
    openai = pytest.importorskip("openai")

    class Completions:
        def create(self, **kwargs):
            content = json.dumps({"hypothesis": "h", "code": "def solve(:"})
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: client)
    monkeypatch.setattr(
        "sys.argv", ["morph", "synthesize", "--model", "test", "--runtime", "bounded-integer-v1"]
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    stderr = capsys.readouterr().err
    assert "invalid Python syntax" in stderr
    assert "Traceback" not in stderr


def test_offline_demo_does_not_open_network(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("offline demo attempted a network connection")

    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr("sys.argv", ["morph", "demo"])
    main()
    assert '"synthetic mock' in capsys.readouterr().out
