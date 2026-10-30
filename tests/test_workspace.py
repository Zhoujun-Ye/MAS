import json

import pytest

from harness.communication import FORMS
from harness.information import InformationHarness
from harness.trace import Trace, read_trace


@pytest.mark.parametrize("form", FORMS)
def test_private_workspace_and_condition_bound_grants(tmp_path, form):
    with Trace(tmp_path / f"{form}.jsonl", form) as trace:
        harness = InformationHarness(["a", "b", "leader"], form, trace)
        record = harness.publish("a", "evidence", dict(text="private fact"))
        with pytest.raises(ValueError, match="not granted"):
            harness.read("leader", record["id"])
        with pytest.raises(ValueError):
            harness.grant("b", "leader", [record["id"]], "m1")
        harness.grant("a", "b", [record["id"]], "m1")
        assert harness.read("b", record["id"])["data"]["text"] == "private fact"



@pytest.mark.parametrize("kind", ["artifact", "memory", "state"])
def test_artifact_grants_and_recovery_cannot_bypass_owner_boundary(tmp_path, kind):
    with Trace(tmp_path / "source.jsonl", "source") as trace:
        harness = InformationHarness(["a", "b"], "agent_team", trace)
        record = harness.publish("a", kind, dict(content="private"))
        with pytest.raises(ValueError, match="not granted"):
            harness.read("b", record["id"])
        harness.grant("a", "b", [record["id"]], "m1")
        assert harness.read("b", record["id"])["data"]["content"] == "private"



def test_immutable_revisions_and_recovery(tmp_path):
    with Trace(tmp_path / "source.jsonl", "source") as trace:
        harness = InformationHarness(["a", "b"], "agent_team", trace)
        old = harness.publish("a", "state", dict(content="quantity=5"))
        new = harness.publish("a", "state", dict(content="quantity=7"), old["id"])
        old["data"]["content"] = "external mutation"
        assert harness.read("a", old["id"])["data"]["content"] == "quantity=5"
        with pytest.raises(ValueError):
            harness.publish("b", "state", dict(content="overwrite"), old["id"])
    with Trace(tmp_path / "recovered.jsonl", "recovered") as trace:
        restored = InformationHarness.recover(["a", "b"], "agent_team", trace,
                                               read_trace(tmp_path / "source.jsonl"))
        assert restored.read("a", old["id"], "recover")["data"]["content"] == "quantity=5"
        assert restored.read("a", new["id"])["data"]["content"] == "quantity=7"
        assert restored.publish("a", "artifact", dict(content="new"))["id"] == "a3"
        with pytest.raises(ValueError, match="Unknown communication"):
            InformationHarness.recover(["a", "b"], "summary", trace, read_trace(tmp_path / "source.jsonl"))


def test_corrupted_record_cannot_be_read_or_recovered(tmp_path):
    with Trace(tmp_path / "corrupt.jsonl", "corrupt") as trace:
        harness = InformationHarness(["a"], "agent_team", trace)
        record = harness.publish("a", "artifact", dict(content="original"))
        record["data"]["content"] = "tampered"
        harness.workspace._records[record["id"]] = json.dumps(record)
        with pytest.raises(ValueError, match="integrity"):
            harness.read("a", record["id"])
        with pytest.raises(ValueError, match="integrity"):
            InformationHarness.recover(["a"], "agent_team", trace,
                                       [dict(type="workspace_record", record=record)])
