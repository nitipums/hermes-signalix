"""Immutable, bounded EOD snapshot selection for the canonical Trend Map.

This store is deliberately independent of the retired setup-candidate read
model.  Publication is the only write path; selection reads one index and the
selected immutable artifact and never calls a market-data or database loader.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping

from artifact_writer import atomic_write_json

MAX_SNAPSHOT_SESSIONS = 3
INDEX_SCHEMA_VERSION = "signalix.trend-map.eod-snapshot-index.v1"
INDEX_NAME = "snapshots.json"
MANIFEST_SCHEMA_VERSION = "signalix.trend-map.eod-snapshot-manifest.v1"
MANIFEST_NAME = "manifest.json"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SnapshotSelectionError(ValueError):
    """A requested snapshot cannot be verified without falling back."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _snapshot_date(value: Any) -> str:
    value = str(value) if value is not None else ""
    if not _DATE.fullmatch(value):
        raise ValueError("invalid snapshot date")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("invalid snapshot date") from error
    return value


def _relative_path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("snapshot artifact path is invalid")
    path = (root / value).resolve()
    if root.resolve() not in path.parents:
        raise ValueError("snapshot artifact path escapes root")
    return path


class TrendMapEodSnapshotStore:
    """Publish and select validated immutable Trend Map EOD artifacts."""

    def __init__(self, root: str | Path, *, validator: Callable[[Mapping[str, Any]], Any] | None = None):
        self.root = Path(root)
        self.validator = validator

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_NAME

    @property
    def manifest_path(self) -> Path:
        return self.root / MANIFEST_NAME

    @staticmethod
    def _validate_index_shape(value: Any) -> dict[str, Any]:
        if (not isinstance(value, dict)
                or value.get("schema_version") != INDEX_SCHEMA_VERSION
                or not isinstance(value.get("sessions"), list)):
            raise SnapshotSelectionError("index_invalid")
        if ("max_sessions" in value
                and value.get("max_sessions") != MAX_SNAPSHOT_SESSIONS):
            raise SnapshotSelectionError("index_invalid")
        if len(value["sessions"]) > MAX_SNAPSHOT_SESSIONS:
            raise SnapshotSelectionError("index_invalid")
        return value

    @classmethod
    def _validate_manifest_shape(cls, value: Any) -> dict[str, Any]:
        if (not isinstance(value, dict)
                or value.get("schema_version") != MANIFEST_SCHEMA_VERSION
                or value.get("max_sessions") != MAX_SNAPSHOT_SESSIONS
                or not isinstance(value.get("sessions"), list)):
            raise SnapshotSelectionError("manifest_invalid")
        sessions = value["sessions"]
        if len(sessions) > MAX_SNAPSHOT_SESSIONS:
            raise SnapshotSelectionError("manifest_invalid")
        if any(not isinstance(entry, Mapping) or not isinstance(entry.get("is_current"), bool)
               for entry in sessions):
            raise SnapshotSelectionError("manifest_invalid")
        if len({entry.get("as_of") for entry in sessions}) != len(sessions):
            raise SnapshotSelectionError("manifest_invalid")
        current_entries = [entry for entry in sessions
                           if isinstance(entry, dict) and entry.get("is_current") is True]
        current = value.get("current")
        if current is not None and not isinstance(current, dict):
            raise SnapshotSelectionError("manifest_mismatch")
        if len(current_entries) > 1 or (current is None) != (not current_entries):
            raise SnapshotSelectionError("manifest_mismatch")
        if current is not None and current != current_entries[0]:
            raise SnapshotSelectionError("manifest_mismatch")
        return value

    def _read_index(self) -> dict[str, Any]:
        # The manifest is the sole reader-visible generation.  snapshots.json
        # remains a compatibility projection for older tooling only.
        if self.manifest_path.exists():
            try:
                return self._validate_manifest_shape(json.loads(
                    self.manifest_path.read_text(encoding="utf-8")))
            except FileNotFoundError:
                return {"schema_version": MANIFEST_SCHEMA_VERSION,
                        "max_sessions": MAX_SNAPSHOT_SESSIONS,
                        "current": None, "sessions": []}
            except (OSError, json.JSONDecodeError) as error:
                raise SnapshotSelectionError("manifest_corrupt") from error
        if self.index_path.exists():
            raise SnapshotSelectionError("manifest_missing")
        return {"schema_version": MANIFEST_SCHEMA_VERSION,
                "max_sessions": MAX_SNAPSHOT_SESSIONS,
                "current": None, "sessions": []}

    def read_index(self) -> dict[str, Any]:
        """Return the validated bounded index (primarily for publisher/tests)."""
        return self._read_index()

    @staticmethod
    def _validate_artifact_shape(artifact: Mapping[str, Any]) -> None:
        required = ("artifact_id", "identity", "as_of", "rows", "universe",
                    "status", "research_only", "actionability", "provenance")
        if any(key not in artifact for key in required):
            raise ValueError("snapshot artifact metadata is incomplete")
        as_of = _snapshot_date(artifact["as_of"])
        identity = artifact.get("identity")
        universe = artifact.get("universe")
        rows = artifact.get("rows")
        if (not isinstance(identity, Mapping) or identity.get("as_of") != as_of
                or not isinstance(rows, list) or not isinstance(universe, Mapping)
                or universe.get("scope") != "marginable_long"
                or not isinstance(universe.get("declared_symbols"), list)
                or universe.get("declared_count") != len(universe["declared_symbols"])
                or artifact.get("status") != "PRODUCTION_READ_ONLY"
                or artifact.get("research_only") is not False
                or artifact.get("actionability") != "NONE"):
            raise ValueError("snapshot artifact metadata is invalid")
        if not identity.get("content_hash") or not identity.get("universe_hash"):
            raise ValueError("snapshot artifact identity is incomplete")

    def _entry(self, artifact: Mapping[str, Any], artifact_path: str, *, is_current: bool) -> dict[str, Any]:
        self._validate_artifact_shape(artifact)
        identity = artifact["identity"]
        return {
            "as_of": artifact["as_of"],
            "artifact_id": artifact["artifact_id"],
            "artifact_path": artifact_path,
            "content_hash": identity["content_hash"],
            "universe_hash": identity["universe_hash"],
            "row_count": len(artifact["rows"]),
            "quality": artifact.get("quality") or artifact.get("data_quality_summary"),
            "provenance": artifact.get("provenance"),
            "is_current": bool(is_current),
        }

    def publish(self, artifact: Mapping[str, Any], *, artifact_path: str, is_current: bool = False) -> dict[str, Any]:
        """Write one immutable artifact and atomically replace the bounded index."""
        self._validate_artifact_shape(artifact)
        path = _relative_path(self.root, artifact_path)
        if path.name != f"{artifact['artifact_id']}.json":
            raise ValueError("snapshot artifact path does not match identity")
        encoded = json.dumps(artifact, sort_keys=True, separators=(",", ":"), default=str).encode()
        if path.exists():
            if path.read_bytes() != encoded:
                raise ValueError("immutable snapshot artifact already differs")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.tmp")
            temporary.write_bytes(encoded)
            try:
                temporary.replace(path)
            finally:
                if temporary.exists():
                    temporary.unlink()

        index = self._read_index()
        sessions = list(index["sessions"])
        # A publication that becomes current clears the old current bit in
        # the same generation as it promotes the new entry.
        entry = self._entry(artifact, artifact_path, is_current=bool(is_current))
        existing = [item for item in sessions if isinstance(item, dict) and item.get("as_of") == entry["as_of"]]
        if existing:
            # A repeated publication may produce a new validated artifact for
            # the same EOD date. Keep the old immutable file, but point the
            # bounded index at the newest artifact.
            sessions = [item for item in sessions if item.get("as_of") != entry["as_of"]]
        sessions.append(entry)
        sessions.sort(key=lambda item: item.get("as_of", ""), reverse=True)
        if is_current:
            sessions = [{**item, "is_current": item is entry or item.get("artifact_id") == entry["artifact_id"]}
                        for item in sessions]
            entry = next(item for item in sessions if item.get("artifact_id") == entry["artifact_id"])
        manifest = {"schema_version": MANIFEST_SCHEMA_VERSION,
                    "max_sessions": MAX_SNAPSHOT_SESSIONS,
                    "current": entry if is_current else next(
                        (item for item in sessions if item.get("is_current") is True), None),
                    "sessions": sessions[:MAX_SNAPSHOT_SESSIONS]}
        # This replace is the only publication point visible to current and
        # historical readers. Compatibility files are deliberately derived.
        atomic_write_json(self.manifest_path, manifest)
        atomic_write_json(self.index_path, {
            "schema_version": INDEX_SCHEMA_VERSION,
            "max_sessions": MAX_SNAPSHOT_SESSIONS,
            "sessions": manifest["sessions"]})
        return entry

    def _select_entry(self, entry: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
        try:
            required = ("as_of", "artifact_id", "artifact_path", "content_hash", "universe_hash", "row_count")
            if any(not entry.get(key) and key != "row_count" for key in required):
                raise ValueError("stale index entry")
            path = _relative_path(self.root, entry["artifact_path"])
            artifact = json.loads(path.read_text(encoding="utf-8"))
            self._validate_artifact_shape(artifact)
            identity = artifact["identity"]
            if (artifact.get("as_of") != entry["as_of"]
                    or artifact.get("artifact_id") != entry["artifact_id"]
                    or identity.get("content_hash") != entry["content_hash"]
                    or identity.get("universe_hash") != entry["universe_hash"]
                    or len(artifact["rows"]) != entry["row_count"]):
                raise ValueError("index artifact mismatch")
            if self.validator is not None:
                self.validator(artifact)
        except FileNotFoundError as error:
            raise SnapshotSelectionError("stale_entry") from error
        except SnapshotSelectionError:
            raise
        except Exception as error:
            reason = "corrupt_artifact" if isinstance(error, (json.JSONDecodeError, ValueError)) else "invalid_entry"
            if "mismatch" in str(error):
                reason = "index_artifact_mismatch"
            raise SnapshotSelectionError(reason) from error
        metadata = {"as_of": entry["as_of"], "kind": kind, "row_count": len(artifact["rows"]),
                    "universe": artifact["universe"], "quality": artifact.get("quality") or artifact.get("data_quality_summary"),
                    "provenance": artifact.get("provenance"), "artifact_id": artifact["artifact_id"],
                    "artifact_path": entry["artifact_path"]}
        return {"artifact": artifact, "snapshot": metadata}

    def select(self, requested_date: str) -> dict[str, Any]:
        """Return exactly the requested verified artifact, or raise a reasoned error."""
        try:
            requested = _snapshot_date(requested_date)
        except ValueError as error:
            raise SnapshotSelectionError("invalid_snapshot_date") from error
        index = self._read_index()
        entry = next((item for item in index["sessions"]
                      if isinstance(item, dict) and item.get("as_of") == requested), None)
        if entry is None:
            raise SnapshotSelectionError("snapshot_not_found")
        return self._select_entry(entry, kind="historical")

    def select_current(self) -> dict[str, Any]:
        index = self._read_index()
        entry = index.get("current")
        if not isinstance(entry, Mapping):
            raise SnapshotSelectionError("current_not_found")
        return self._select_entry(entry, kind="current")
