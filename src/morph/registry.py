"""Append-only experiment record storage."""

import hashlib
import json
import sqlite3
from pathlib import Path


def save(path: Path, report: dict) -> int:
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS experiments (id INTEGER PRIMARY KEY, "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, report TEXT NOT NULL)"
        )
        cursor = db.execute(
            "INSERT INTO experiments (report) VALUES (?)", (json.dumps(report, sort_keys=True),)
        )
        assert cursor.lastrowid is not None
        return cursor.lastrowid


def _schema(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS patches (id TEXT PRIMARY KEY, payload TEXT NOT NULL, "
        "validation_status TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS patch_events (id INTEGER PRIMARY KEY, "
        "previous_id TEXT, next_id TEXT, action TEXT NOT NULL, approved_by TEXT NOT NULL, "
        "reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS active_version (singleton INTEGER PRIMARY KEY "
        "CHECK(singleton = 1), patch_id TEXT)"
    )
    db.execute("INSERT OR IGNORE INTO active_version VALUES (1, NULL)")
    db.execute(
        "CREATE TABLE IF NOT EXISTS patch_evidence (patch_id TEXT PRIMARY KEY, "
        "digest TEXT NOT NULL)"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS patch_provenance (patch_id TEXT PRIMARY KEY, digest TEXT NOT NULL)"
    )


def _digest(evidence: dict) -> str:
    return hashlib.sha256(
        json.dumps(evidence, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def _validate_evidence(evidence: dict) -> None:
    from morph.core import Run
    from morph.experiment import Observation, compare

    def decode(items):
        result = []
        for item in items:
            run = Run(**item["run"])
            passed = run.error is None and run.answer == item["expected"]
            if (
                type(item["passed"]) is not bool
                or item["passed"] != passed
                or run.task_id != item["task_id"]
            ):
                raise ValueError("inconsistent evidence")
            result.append(
                Observation(
                    item["task_id"],
                    item["category"],
                    item["split"],
                    item["expected"],
                    run,
                    passed,
                    tuple(item["values"]),
                )
            )
        return result

    try:
        recalculated = compare(
            decode(evidence["baseline_runs"]), decode(evidence["candidate_runs"])
        )
        if _digest(recalculated) != _digest(evidence):
            raise ValueError("inconsistent evidence")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid validation evidence") from exc


def register_patch(
    path: Path,
    patch: dict,
    validation_status: str,
    *,
    evidence: dict | None = None,
    provenance: dict | None = None,
) -> None:
    patch_id = patch.get("id")
    if not isinstance(patch_id, str) or not patch_id.strip():
        raise ValueError("patch ID required")
    if validation_status not in {"inconclusive", "rejected", "eligible_for_review"}:
        raise ValueError("invalid validation status")
    if validation_status == "eligible_for_review" and evidence is None:
        raise ValueError("eligible patch requires validation evidence")
    if evidence is not None and evidence.get("status") != validation_status:
        raise ValueError("evidence status does not match")
    if evidence is not None:
        from morph.patches import patch_fingerprint

        _validate_evidence(evidence)
        fingerprint = f"sha256:{patch_fingerprint(patch)}"
        if any(
            f"patch:{patch_id}" not in item["run"]["trace"]
            or fingerprint not in item["run"]["trace"]
            for item in evidence["candidate_runs"]
        ):
            raise ValueError("evidence does not match patch identity")
    if provenance is not None and (
        provenance.get("patch") != patch
        or _digest(provenance.get("comparison", {})) != _digest(evidence or {})
    ):
        raise ValueError("report provenance does not match patch evidence")
    with sqlite3.connect(path) as db:
        _schema(db)
        db.execute(
            "INSERT INTO patches VALUES (?, ?, ?)",
            (patch_id, json.dumps(patch, sort_keys=True), validation_status),
        )
        if evidence is not None:
            db.execute("INSERT INTO patch_evidence VALUES (?, ?)", (patch_id, _digest(evidence)))
        if provenance is not None:
            db.execute(
                "INSERT INTO patch_provenance VALUES (?, ?)", (patch_id, _digest(provenance))
            )


def matches_evidence(path: Path, patch_id: str, evidence: dict) -> bool:
    with sqlite3.connect(path) as db:
        _schema(db)
        row = db.execute(
            "SELECT digest FROM patch_evidence WHERE patch_id = ?", (patch_id,)
        ).fetchone()
    return row is not None and row[0] == _digest(evidence)


def matches_provenance(path: Path, patch_id: str, report: dict) -> bool:
    with sqlite3.connect(path) as db:
        _schema(db)
        row = db.execute(
            "SELECT digest FROM patch_provenance WHERE patch_id = ?", (patch_id,)
        ).fetchone()
    return row is not None and row[0] == _digest(report)


def _change(path: Path, patch_id: str | None, approved_by: str, reason: str, action: str) -> None:
    if not approved_by.strip() or not reason.strip():
        raise ValueError("explicit approval and reason required")
    with sqlite3.connect(path, isolation_level=None) as db:
        db.execute("BEGIN IMMEDIATE")
        _schema(db)
        current = db.execute("SELECT patch_id FROM active_version WHERE singleton = 1").fetchone()[
            0
        ]
        if patch_id is not None:
            row = db.execute(
                "SELECT validation_status FROM patches WHERE id = ?", (patch_id,)
            ).fetchone()
            if row is None or row[0] != "eligible_for_review":
                raise ValueError("patch must be eligible for review")
            if (
                action == "rollback"
                and not db.execute(
                    "SELECT 1 FROM patch_events WHERE next_id = ?", (patch_id,)
                ).fetchone()
            ):
                raise ValueError("rollback target must have been previously active")
        db.execute("UPDATE active_version SET patch_id = ? WHERE singleton = 1", (patch_id,))
        db.execute(
            "INSERT INTO patch_events (previous_id, next_id, action, approved_by, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (current, patch_id, action, approved_by, reason),
        )
        db.commit()


def activate(path: Path, patch_id: str, *, approved_by: str, reason: str) -> None:
    _change(path, patch_id, approved_by, reason, "activate")


def rollback(path: Path, patch_id: str | None, *, approved_by: str, reason: str) -> None:
    _change(path, patch_id, approved_by, reason, "rollback")


def active_patch(path: Path) -> dict | None:
    with sqlite3.connect(path) as db:
        _schema(db)
        row = db.execute(
            "SELECT patches.payload FROM active_version JOIN patches "
            "ON active_version.patch_id = patches.id WHERE singleton = 1"
        ).fetchone()
    return json.loads(row[0]) if row else None
