# Privacy and data flow

The distributed source contains generic task instructions and synthetic test examples. It contains no personal conversation transcript. MORPH has no integration that reads a chat application's conversations, no background uploader and no telemetry endpoint.

| Path | Network | Data written locally |
|---|---|---|
| `demo`, `benchmark`, bounded example | None | JSON on stdout; SQLite only when requested |
| Bounded interpreter | None; no I/O language primitives | Returned integer or failure |
| `local-baseline` | Fixed Ollama loopback endpoint; environment proxies disabled | Model identity, tasks, prompts, completions, outcomes and sampling configuration |
| `synthesize` | Configured provider after runtime preflight | Candidate and comparison; optional SQLite report |
| Registry and router | None | Patch/evidence hashes and metadata events |
| `holdout` | Provider if required by the baseline; selected execution runtime | Reservation fingerprints and aggregate results |

Remote synthesis sends development failure evidence to the selected provider. A model-backed agent sends its supplied inputs; its arithmetic request does not contain the reference answer. Provider policies apply to data sent to that provider.

Keys are read by the optional SDK and are not intentionally serialized into reports. Do not put secrets in task text, code, filenames, metadata or model responses: these fields may be stored verbatim. Local files are not encrypted. Anyone with access to a report or SQLite database may inspect its task data. The registry is an audit aid, not an access-control system.

## Publication policy

Public releases exclude raw request/response files, local databases, `.env` files, runtime logs and attachments. `reports/README.md` contains curated aggregate measurements only. Generic source prompt templates remain visible because they define the studied procedure; personal messages are not templates.

Generated files belong in ignored `local-results/` or another private directory. The release audit checks the tracked tree and reachable publication history for forbidden artifacts and common secret/path patterns. These checks reduce accidental disclosure; they cannot prove that arbitrary text is non-sensitive.

Review custom tasks, model responses, source paths, endpoints and metadata before sharing them. A key placeholder in `.env.example` is documentation; a real key must never be committed.
