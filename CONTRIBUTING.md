# Contributing

Use the project virtual environment and install `python -m pip install -e '.[dev,openai]'`. Run `python -m pytest`, `python -m ruff check .`, `python -m ruff format --check .` and `python -m build`.

Default tests use offline fixtures and in-process HTTP transports, not paid API calls. Two Docker integration checks are skipped unless `MORPH_DOCKER_TEST=1` is explicitly set on an isolated host with a trusted local image. A skip is not a passed integration check.

For execution changes, cover unsupported syntax, resource limits and relevant regressions. For evaluation changes, preserve split boundaries and immutable outcomes; do not weaken a verifier to improve a score. Label mock/synthetic experiments and report negative results.

Use `python scripts/audit_release.py --history` before publication from a clean release checkout. The audit deliberately rejects raw local experiment files and histories containing them. Check local Markdown links and verify installation from a built wheel with `python scripts/smoke_wheel.py PATH_TO_WHEEL`.

Keep private data in ignored `local-results/`. Never submit credentials, conversation transcripts, private tasks or raw model logs in issues/PRs. Use a minimal synthetic reproduction. Follow [SECURITY.md](SECURITY.md) for execution risks and vulnerability reports.
