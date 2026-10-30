"""Private-by-default workspace and condition-aware information access.

Storage is not model context. Only explicit tool results and delivered handoffs
materialize records. Integrity verification never asserts semantic correctness.
"""
import json

from .config import digest


class SharedWorkspace:
    """Immutable, version-addressed records; serialized values prevent alias writes."""

    def __init__(self):
        self._records = {}
        self._counts = {"e": 0, "a": 0}

    def put(self, owner, kind, data, previous=None):
        prefix = "e" if kind == "evidence" else "a"
        self._counts[prefix] += 1
        key = f"{prefix}{self._counts[prefix]}"
        record = dict(id=key, owner=owner, kind=kind, data=data, previous=previous)
        record["digest"] = digest(record)
        self._records[key] = json.dumps(record, ensure_ascii=False)
        return self.get(key)

    def get(self, key):
        record = json.loads(self._records[key])
        checksum = record.pop("digest")
        if digest(record) != checksum or record["id"] != key:
            raise ValueError("Workspace integrity check failed")
        return dict(record, digest=checksum)

    def restore_record(self, record):
        key = record["id"]
        if key in self._records:
            raise ValueError("Duplicate workspace record")
        self._records[key] = json.dumps(record, ensure_ascii=False)
        try:
            self.get(key)
            prefix, number = key[0], int(key[1:])
            if prefix not in self._counts or number <= self._counts[prefix]:
                raise ValueError("Invalid workspace record sequence")
        except Exception:
            del self._records[key]
            raise
        self._counts[prefix] = number


class InformationHarness:
    """The only agent-facing access path to the shared workspace."""

    def __init__(self, roles, form, trace):
        self.workspace = SharedWorkspace()
        self.access = {role: set() for role in roles}
        self.form, self.trace = form, trace

    @property
    def evidence(self):
        return {key: self.workspace.get(key)["data"] for key in self.workspace._records if key.startswith("e")}

    def publish(self, owner, kind, data, previous=None):
        if owner not in self.access or kind not in ("evidence", "artifact", "memory", "state"):
            raise ValueError("Unknown owner or record kind")
        if previous is not None:
            prior = self.authorized(owner, previous)
            if prior["owner"] != owner or prior["kind"] != kind or kind == "evidence":
                raise ValueError("Only the owner may append a matching artifact revision")
        record = self.workspace.put(owner, kind, data, previous)
        self.access[owner].add(record["id"])
        self.trace.emit("workspace_record", record=record, form=self.form)
        return record

    def authorized(self, role, key):
        if key not in self.access.get(role, ()):
            raise ValueError("Record not granted to this recipient")
        return self.workspace.get(key)

    def validate_grants(self, sender, ids, prefix):
        if not isinstance(ids, list) or not all(isinstance(key, str) and key.startswith(prefix) for key in ids):
            raise ValueError("Invalid workspace reference list")
        for key in ids:
            self.authorized(sender, key)

    def grant(self, sender, recipient, ids, message_id):
        if recipient not in self.access:
            raise ValueError("Unknown recipient")
        for key in ids:
            self.authorized(sender, key)
        if ids and self.form not in ("document_retrieval", "adaptive"):
            raise ValueError("Original-record grants disabled in this condition")
        self.access[recipient].update(ids)
        if ids:
            self.trace.emit("workspace_grant", sender=sender, recipient=recipient,
                            ids=ids, message_id=message_id, form=self.form)

    def read(self, role, key, operation="read"):
        record = self.authorized(role, key)
        if record["owner"] != role and self.form not in ("document_retrieval", "adaptive"):
            raise ValueError("Original-record reads disabled in this condition")
        self.trace.emit("workspace_read", agent=role, record_id=key, operation=operation,
                        digest=record["digest"])
        return record

    def search(self, role, query, kind=None):
        if self.form != "adaptive":
            raise ValueError("Workspace search disabled in this condition")
        if not query.strip():
            raise ValueError("A non-empty exact text fragment is required")
        matches = []
        for key in sorted(self.access[role]):
            record = self.authorized(role, key)
            if kind == "non_evidence" and record["kind"] == "evidence":
                continue
            if kind not in (None, "non_evidence") and record["kind"] != kind:
                continue
            text = record["data"]["text"] if record["kind"] == "evidence" else json.dumps(record["data"], ensure_ascii=False)
            if query.casefold() in text.casefold():
                matches.append(self.read(role, key, "search"))
        return matches

    def visible_ids(self, role, prefix):
        return sorted(key for key in self.access[role] if key.startswith(prefix))

    @classmethod
    def recover(cls, roles, form, trace, events):
        """Rebuild workspace and ACLs, not conversations or paid execution state."""
        restored = cls(roles, form, trace)
        for event in events:
            if event["type"] in ("workspace_record", "workspace_grant") and event.get("form", form) != form:
                raise ValueError("Recovery cannot bypass the original communication condition")
            if event["type"] == "workspace_record":
                record = event["record"]
                if record["owner"] not in restored.access:
                    raise ValueError("Unknown workspace owner")
                restored.workspace.restore_record(record)
                restored.access[record["owner"]].add(record["id"])
            elif event["type"] == "workspace_grant":
                if form not in ("document_retrieval", "adaptive"):
                    raise ValueError("Recovery cannot bypass the communication condition")
                for key in event["ids"]:
                    restored.authorized(event["sender"], key)
                restored.access[event["recipient"]].update(event["ids"])
        return restored
