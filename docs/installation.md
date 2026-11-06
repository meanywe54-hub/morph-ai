# Installation

Install [Python 3.11 or newer](https://www.python.org/downloads/) and [Git](https://git-scm.com/downloads). The offline path needs no Docker, WSL, API key or model. MORPH does not install system services or change operating-system settings.

```sh
git clone https://github.com/meanywe54-hub/morph-ai.git
cd morph-ai
python -m venv .venv
```

On Windows, use `py -3` instead of `python` if that is how Python is installed. Check `python --version` first. Use a shell opened in the cloned directory.

## Windows PowerShell

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m morph.cli demo
.\.venv\Scripts\python.exe examples/bounded_evolution.py
```

No environment activation is required, so no execution-policy change is needed.

## Linux and macOS

```sh
.venv/bin/python -m pip install -e .
.venv/bin/python -m morph.cli demo
.venv/bin/python examples/bounded_evolution.py
```

If the system Python has no `venv`/`ensurepip`, install the corresponding component through the operating system's documented Python installation process. Do not use a system-wide `sudo pip install` for this project.

## Optional extras

Use the environment's Python for all commands below:

```sh
python -m pip install -e '.[openai]'
python -m pip install -e '.[dev,openai]'
```

`openai` adds the compatible provider SDK and HTTP transport. `dev` adds pytest, Ruff and package build tooling. The core has no third-party runtime dependency. The project is installed from source; no PyPI publication is claimed.

For Ollama, use its [official installation guide](https://docs.ollama.com/quickstart), an already downloaded model and a locally running server. Model downloads and inference are explicit operator actions. See [experiment instructions](real-model-experiment.md).

## Verify and troubleshoot

`python -m morph.cli --help` should list the available commands. `demo` should print JSON with `mode` containing `synthetic mock` and `comparison.status` equal to `inconclusive`.

- `No module named morph`: run installation with the same environment Python you use to launch commands.
- `No module named openai`: install `.[openai]` into that environment.
- Docker unavailable: choose the offline examples or `bounded-integer-v1`; Docker has no silent host-execution fallback.
- Local Ollama refused connection: verify that its server is running on `127.0.0.1:11434` and the named model is already installed.
- Existing output file: local measurements refuse overwrites. Choose a new private output path.
- `inconclusive`: inspect sample size, distinct inputs, errors and gains; this is a legitimate evaluation outcome.

Use [the walkthrough](walkthrough.md) for the experiment lifecycle and [SECURITY.md](../SECURITY.md) for runtime limitations.
