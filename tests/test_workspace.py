import json

import pytest

from harness.information import InformationHarness
from harness.trace import Trace, read_trace


@pytest.mark.parametrize("form", ["full_context", "summary", "structured", "document_retrieval", "adaptive"])
def test_private_workspace_and_condition_bound_grants(tmp_path, form):
    with Trace(tmp_path / f"{form}.jsonl", form) as trace:
        harness = InformationHarness(["a", "b", "leader"], form, trace)
        record = harness.publish("a", "memory", dict(content="private fact"))
        with pytest.raises(ValueError, match="not granted"):
            harness.read("leader", record["id"])
        with pytest.raises(ValueError):
            harness.grant("b", "leader", [record["id"]], "m1")
        if form in ("document_retrieval", "adaptive"):
            harness.grant("a", "b", [record["id"]], "m1")
            assert harness.read("b", record["id"])["data"]["content"] == "private fact"
            with pytest.raises(ValueError):
                harness.read("leader", record["id"])
        else:
            with pytest.raises(ValueError, match="disabled"):
                harness.grant("a", "b", [record["id"]], "m1")


def test_immutable_revisions_no_implicit_grants_and_recovery(tmp_path):
    with Trace(tmp_path / "source.jsonl", "source") as trace:
        harness = InformationHarness(["a", "b"], "adaptive", trace)
        old = harness.publish("a", "state", dict(content="quantity=5"))
        harness.grant("a", "b", [old["id"]], "m1")
        new = harness.publish("a", "state", dict(content="quantity=7"), old["id"])
        old["data"]["content"] = "external mutation"
        assert harness.read("b", old["id"])["data"]["content"] == "quantity=5"
        with pytest.raises(ValueError):
            harness.read("b", new["id"])
        with pytest.raises(ValueError, match="Only the owner"):
            harness.publish("b", "state", dict(content="overwrite"), old["id"])
        assert harness.search("b", "quantity=7") == []
        assert len(harness.search("b", "quantity=5")) == 1
    with Trace(tmp_path / "recovered.jsonl", "recovered") as trace:
        restored = InformationHarness.recover(["a", "b"], "adaptive", trace, read_trace(tmp_path / "source.jsonl"))
        assert restored.read("b", old["id"], "recover")["data"]["content"] == "quantity=5"
        with pytest.raises(ValueError):
            restored.read("b", new["id"])
        assert restored.publish("a", "artifact", dict(content="new"))["id"] == "a3"
        with pytest.raises(ValueError, match="bypass"):
            InformationHarness.recover(["a", "b"], "summary", trace, read_trace(tmp_path / "source.jsonl"))
        with pytest.raises(ValueError, match="bypass"):
            InformationHarness.recover(["a", "b"], "document_retrieval", trace, read_trace(tmp_path / "source.jsonl"))


def test_corrupted_record_cannot_be_read_or_recovered(tmp_path):
    with Trace(tmp_path / "corrupt.jsonl", "corrupt") as trace:
        harness = InformationHarness(["a"], "adaptive", trace)
        record = harness.publish("a", "artifact", dict(content="original"))
        record["data"]["content"] = "tampered"
        harness.workspace._records[record["id"]] = json.dumps(record)
        with pytest.raises(ValueError, match="integrity"):
            harness.read("a", record["id"])
        with pytest.raises(ValueError, match="integrity"):
            InformationHarness.recover(["a"], "adaptive", trace, [dict(type="workspace_record", record=record)])
