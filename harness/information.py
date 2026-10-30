"""Frozen sender policy and private-by-default information access.

Storage is not model context. Only explicit tool results and delivered handoffs
materialize records. Integrity verification never asserts semantic correctness.
"""
import json
from dataclasses import asdict, dataclass

from .config import digest
from .communication import FORMS


@dataclass(frozen=True)
class CommunicationPolicy:
    """Versioned sender-side instructions, not executable runtime mutations."""
    version: str = "free-collaboration-v1"
    instructions: str = ("Communicate with any allowed teammate whenever you judge it useful. "
                         "Choose the content and form yourself: discussion, questions, objections, code or evidence references. "
                         "Use information available in your own context; do not invent observations.")

    @property
    def manifest(self):
        return asdict(self)


@dataclass(frozen=True)
class OutgoingMessage:
    sender: str
    recipient: str
    content: str
    evidence_ids: tuple[str, ...]
    artifact_ids: tuple[str, ...]
    requires_reply: bool


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

    def __init__(self, roles, form, trace, policy=None):
        if form not in FORMS:
            raise ValueError("Unknown communication form")
        self.workspace = SharedWorkspace()
        self.access = {role: set() for role in roles}
        self.observed = {role: set() for role in self.access}
        self.form, self.trace = form, trace
        self.policy = CommunicationPolicy() if policy is None else policy
        if (type(self.policy) is not CommunicationPolicy
                or not isinstance(self.policy.version, str) or not self.policy.version.strip()
                or not isinstance(self.policy.instructions, str) or not self.policy.instructions.strip()):
            raise ValueError("Expected a frozen sender policy")

    def prepare_message(self, sender, recipient, content, evidence_ids, artifact_ids, requires_reply=False):
        """Single boundary for explicit sends, corrections and submission reports.

        The sender constructs content under the frozen policy. Transport never
        rewrites it, expands references or reads anyone's private context.
        """
        if sender not in self.access or recipient not in self.access or sender == recipient:
            raise ValueError("Recipient must be a different selected teammate")
        if not isinstance(content, str) or not content.strip() or type(requires_reply) is not bool:
            raise ValueError("Nonempty message and boolean reply flag required")
        self.validate_grants(sender, evidence_ids, "e")
        self.validate_grants(sender, artifact_ids, "a")
        return OutgoingMessage(sender, recipient, content, tuple(evidence_ids), tuple(artifact_ids), requires_reply)

    @property
    def raw_evidence_enabled(self):
        return True

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
        self.observed[owner].add(record["id"])
        self.trace.emit("workspace_record", record=record, form=self.form)
        return record

    def authorized(self, role, key):
        if key not in self.access.get(role, ()):
            raise ValueError("Record not granted to this recipient")
        record = self.workspace.get(key)
        return record

    def validate_grants(self, sender, ids, prefix):
        if not isinstance(ids, list) or not all(isinstance(key, str) and key.startswith(prefix) for key in ids):
            raise ValueError("Invalid workspace reference list")
        for key in ids:
            self.authorized(sender, key)

    def validate_transfer(self, sender, recipient, ids):
        if recipient not in self.access:
            raise ValueError("Unknown recipient")
        for key in ids:
            self.authorized(sender, key)
    def grant(self, sender, recipient, ids, message_id):
        self.validate_transfer(sender, recipient, ids)
        self.access[recipient].update(ids)
        if ids:
            self.trace.emit("workspace_grant", sender=sender, recipient=recipient,
                            ids=ids, message_id=message_id, form=self.form)

    def read(self, role, key, operation="read"):
        record = self.authorized(role, key)
        if record["owner"] != role and not self.raw_evidence_enabled:
            raise ValueError("Original-record reads disabled in this condition")
        self.trace.emit("workspace_read", agent=role, record_id=key, operation=operation,
                        digest=record["digest"])
        if operation != "verify":
            self.observed[role].add(key)
        return record

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
                restored.observed[record["owner"]].add(record["id"])
            elif event["type"] == "workspace_grant":
                restored.validate_transfer(event["sender"], event["recipient"], event["ids"])
                restored.access[event["recipient"]].update(event["ids"])
            elif event["type"] == "workspace_read" and event.get("operation") != "verify":
                restored.authorized(event["agent"], event["record_id"])
                restored.observed[event["agent"]].add(event["record_id"])
        return restored
