"""Compare one development prompt on native Ollama CPU inference; no generated code runs."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

request = {
    "model": "qwen2.5-coder:7b",
    "messages": [
        {
            "role": "user",
            "content": "Add all of the following signed integers. Return only a JSON object with an integer field named answer. Integers: [5, -2]",
        }
    ],
    "stream": False,
    "format": "json",
    "options": {"num_gpu": 0, "num_ctx": 2048, "temperature": 0, "seed": 0, "num_predict": 128},
}
path = Path("reports/2026-11-07-qwen25-cpu-diagnostic.json")
with path.open("x", encoding="utf-8") as stream:
    json.dump({"status": "running", "request": request}, stream, indent=2)
with httpx.Client(trust_env=False, timeout=180) as client:
    response = client.post("http://127.0.0.1:11434/api/chat", json=request)
    response.raise_for_status()
    payload = response.json()
path.write_text(
    json.dumps(
        {
            "created_at": datetime.now(UTC).isoformat(),
            "status": "completed",
            "request": request,
            "response": payload,
            "limitation": "Single development example; API and runner options differ from baseline",
        },
        indent=2,
    ),
    encoding="utf-8",
)
print(json.dumps({"output": str(path), "answer": payload["message"]["content"]}))
