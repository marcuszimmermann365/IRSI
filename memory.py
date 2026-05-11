"""
Memory Store with lifecycle + V10.2 locked read-modify-write semantics
======================================================================
Memory items have lifecycle states:
  proposed | provisional | consolidated | challenged | revoked | rejected

V10.2 closes the v10.1 lost-update window: every mutation reloads the latest
JSON state while holding the file lock, applies its change, then atomically
writes the result.  This is still not a production database, but it prevents
stale in-memory state from overwriting concurrent updates in the JSON backend.
"""

import json
import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from storage import atomic_write_json, file_lock
from version import SCHEMA_VERSION


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:

    def __init__(self, path="memory_store.json"):
        self.path = path
        if os.path.exists(path):
            with file_lock(self.path):
                self.data = self._load_unlocked()
        else:
            self.data = self._empty_data()
            with file_lock(self.path):
                if os.path.exists(path):
                    self.data = self._load_unlocked()
                else:
                    self._write_unlocked(self.data)

    def _empty_data(self):
        return {
            "schema_version": SCHEMA_VERSION,
            "created_at": utc_now_iso(),
            "candidate": [],
            "consolidated": [],
            "archive": [],
        }

    def _normalize(self, data):
        data = data or self._empty_data()
        data.setdefault("schema_version", SCHEMA_VERSION)
        data.setdefault("created_at", utc_now_iso())
        data.setdefault("candidate", [])
        data.setdefault("consolidated", [])
        data.setdefault("archive", [])
        return data

    def _load_unlocked(self):
        if not os.path.exists(self.path):
            return self._empty_data()
        with open(self.path, "r", encoding="utf-8") as f:
            return self._normalize(json.load(f))

    def _write_unlocked(self, data):
        data = self._normalize(data)
        data["updated_at"] = utc_now_iso()
        atomic_write_json(self.path, data)

    def refresh(self):
        with file_lock(self.path):
            self.data = self._load_unlocked()
            return self.data

    def _mutate_locked(self, mutator):
        with file_lock(self.path):
            data = self._load_unlocked()
            result = mutator(data)
            self._write_unlocked(data)
            self.data = data
            return result

    def _save(self):
        """Compatibility method: persist current state under lock.

        New mutation methods use _mutate_locked so they do not overwrite with
        stale state.  _save is retained for external callers that modified
        self.data directly, but should not be used by new code.
        """
        with file_lock(self.path):
            self._write_unlocked(self.data)

    # ── Candidate management ──────────────────────────────────────────

    def add_candidate(self, content, source, kind, metadata=None):
        def mutate(data):
            entry = {
                "id": str(uuid.uuid4()),
                "content": content,
                "source": source,
                "kind": kind,
                "metadata": metadata or {},
                "observations": 1,
                "status": "proposed",
                "review_count": 0,
                "challenge_count": 0,
                "active": True,
            }
            data["candidate"].append(entry)
            return deepcopy(entry)
        return self._mutate_locked(mutate)

    def reinforce_candidate(self, content):
        def mutate(data):
            for entry in data["candidate"]:
                if entry["content"] == content and entry.get("active", True):
                    entry["observations"] = entry.get("observations", 1) + 1
                    if entry["status"] == "proposed" and entry["observations"] >= 2:
                        entry["status"] = "provisional"
                    return deepcopy(entry)
            return None
        return self._mutate_locked(mutate)

    def mark_candidate_status(self, candidate_id, status):
        def mutate(data):
            for entry in data["candidate"]:
                if entry["id"] == candidate_id:
                    entry["status"] = status
                    return deepcopy(entry)
            return None
        return self._mutate_locked(mutate)

    def increment_review_count(self, candidate_id):
        def mutate(data):
            for entry in data["candidate"]:
                if entry["id"] == candidate_id:
                    entry["review_count"] = entry.get("review_count", 0) + 1
                    return deepcopy(entry)
            return None
        return self._mutate_locked(mutate)

    def get_pending_candidates(self):
        self.refresh()
        return [deepcopy(c) for c in self.data["candidate"]
                if c.get("status") in ("proposed", "provisional")]

    def get_review_candidates(self):
        self.refresh()
        return [deepcopy(c) for c in self.data["candidate"]
                if c.get("status") == "review"]

    # ── Consolidation ─────────────────────────────────────────────────

    def is_already_consolidated(self, content):
        self.refresh()
        for entry in self.data["consolidated"]:
            if entry.get("active", True) and entry["content"] == content:
                return True
        return False

    def add_consolidated(self, candidate_entry, review_info):
        def mutate(data):
            entry = {
                "id": candidate_entry["id"],
                "content": candidate_entry["content"],
                "source": candidate_entry["source"],
                "kind": candidate_entry["kind"],
                "metadata": candidate_entry.get("metadata", {}),
                "observations": candidate_entry.get("observations", 1),
                "review_info": review_info,
                "status": "consolidated",
                "challenge_count": 0,
                "active": True,
            }
            data["consolidated"].append(entry)
            return deepcopy(entry)
        return self._mutate_locked(mutate)

    # ── Challenge and Revoke ──────────────────────────────────────────

    def challenge_memory(self, memory_id, reason, evidence=None):
        def mutate(data):
            for entry in data["consolidated"]:
                if entry["id"] == memory_id and entry.get("active", True):
                    entry["status"] = "challenged"
                    entry["challenge_count"] = entry.get("challenge_count", 0) + 1
                    entry["challenge_reason"] = reason
                    entry["challenge_evidence"] = evidence
                    return deepcopy(entry)
            return None
        return self._mutate_locked(mutate)

    def revoke_memory(self, memory_id, reason):
        def mutate(data):
            for entry in data["consolidated"]:
                if entry["id"] == memory_id and entry.get("active", True):
                    entry["active"] = False
                    entry["status"] = "revoked"
                    entry["revoke_reason"] = reason
                    data["archive"].append(dict(entry))
                    return deepcopy(entry)
            return None
        return self._mutate_locked(mutate)

    def get_challenged_memories(self):
        self.refresh()
        return [deepcopy(m) for m in self.data["consolidated"]
                if m.get("status") == "challenged" and m.get("active", True)]

    def get_active_consolidated(self):
        self.refresh()
        return [deepcopy(m) for m in self.data["consolidated"]
                if m.get("active", True) and m.get("status") == "consolidated"]

    def auto_challenge_contradictions(self, new_content, new_kind):
        def mutate(data):
            challenged = []
            for m in data["consolidated"]:
                if not m.get("active", True):
                    continue
                existing = m.get("content", "").lower()
                new = new_content.lower()
                contradiction = False
                if (("improve" in new and "reduce" in existing) or
                        ("reduce" in new and "improve" in existing)):
                    contradiction = True
                if (("robust" in new and "fragile" in existing) or
                        ("fragile" in new and "robust" in existing)):
                    contradiction = True
                if contradiction:
                    m["status"] = "challenged"
                    m["challenge_count"] = m.get("challenge_count", 0) + 1
                    m["challenge_reason"] = "contradicted_by_new_evidence"
                    m["challenge_evidence"] = {
                        "new_content": new_content,
                        "new_kind": new_kind,
                    }
                    challenged.append(m["id"])
            return challenged
        return self._mutate_locked(mutate)

    def lifecycle_stats(self):
        self.refresh()
        candidates = self.data["candidate"]
        consolidated = self.data["consolidated"]
        archive = self.data.get("archive", [])
        return {
            "proposed": sum(1 for c in candidates if c.get("status") == "proposed"),
            "provisional": sum(1 for c in candidates if c.get("status") == "provisional"),
            "consolidated": sum(1 for c in consolidated
                                if c.get("active") and c.get("status") == "consolidated"),
            "challenged": sum(1 for c in consolidated
                              if c.get("active") and c.get("status") == "challenged"),
            "revoked": len(archive),
            "rejected": sum(1 for c in candidates if c.get("status") == "rejected"),
        }
