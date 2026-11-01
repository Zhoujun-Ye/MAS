import copy
import json
from types import SimpleNamespace

import pytest

from harness.container_contract import validate_data_container


def setup_container(tmp_path, monkeypatch):
    dataset, work = tmp_path / "data", tmp_path / "work"
    dataset.mkdir()
    (dataset / "values.csv").write_text("value\n1\n")
    work.mkdir()
    (work / ".git").mkdir()
    info = {"State": {"Running": True}, "Image": "sha256:fixture",
        "HostConfig": {"NetworkMode": "none", "Privileged": False},
        "Mounts": [{"Type": "bind", "Source": str(dataset), "Destination": "/data", "RW": False},
                   {"Type": "bind", "Source": str(work), "Destination": "/workspace", "RW": True}]}
    def check_output(command):
        if command[0] == "docker":
            return json.dumps([info]).encode()
        assert command == ["git", "-C", str(work), "rev-list", "--all"]
        return b""
    monkeypatch.setattr("harness.container_contract.subprocess.check_output", check_output)
    return SimpleNamespace(container="test", workdir="/workspace"), dataset, work, info


def test_container_provenance_is_actual_data_hash(tmp_path, monkeypatch):
    workspace, dataset, _, _ = setup_container(tmp_path, monkeypatch)
    result = validate_data_container(workspace, dataset)
    import hashlib
    assert result["dataset_files"]["values.csv"]["sha256"] == hashlib.sha256(b"value\n1\n").hexdigest()
    assert result["image_id"] == "sha256:fixture"


def test_mount_order_is_not_environment_drift(tmp_path, monkeypatch):
    workspace, dataset, _, info = setup_container(tmp_path, monkeypatch)
    first = validate_data_container(workspace, dataset)
    info["Mounts"].reverse()
    assert validate_data_container(workspace, dataset) == first


@pytest.mark.parametrize("setting,value", [("NetworkMode", "host"), ("Privileged", True),
    ("PidMode", "host"), ("IpcMode", "host"), ("CapAdd", ["SYS_ADMIN"]), ("Devices", ["gpu"])])
def test_unsafe_container_modes_rejected(tmp_path, monkeypatch, setting, value):
    workspace, dataset, _, info = setup_container(tmp_path, monkeypatch)
    info["HostConfig"][setting] = value
    with pytest.raises(ValueError, match="network-disabled"):
        validate_data_container(workspace, dataset)


def test_mount_write_and_reference_leakage_rejected(tmp_path, monkeypatch):
    workspace, dataset, work, info = setup_container(tmp_path, monkeypatch)
    mounts = copy.deepcopy(info["Mounts"])
    info["Mounts"][0]["RW"] = True
    with pytest.raises(ValueError, match="read-only"):
        validate_data_container(workspace, dataset)
    info["Mounts"] = copy.deepcopy(mounts)
    info["Mounts"].append({"Destination": "/solutions"})
    with pytest.raises(ValueError, match="Only"):
        validate_data_container(workspace, dataset)
    info["Mounts"] = mounts
    (work / "answer.txt").write_text("reference answer")
    with pytest.raises(ValueError, match="fresh"):
        validate_data_container(workspace, dataset)


def test_dataset_symlink_rejected(tmp_path, monkeypatch):
    workspace, dataset, work, _ = setup_container(tmp_path, monkeypatch)
    (dataset / "leak").symlink_to(work)
    with pytest.raises(ValueError, match="symlinks"):
        validate_data_container(workspace, dataset)


def test_hidden_git_history_rejected(tmp_path, monkeypatch):
    workspace, dataset, _, info = setup_container(tmp_path, monkeypatch)
    monkeypatch.setattr("harness.container_contract.subprocess.check_output",
        lambda command: json.dumps([info]).encode() if command[0] == "docker" else b"old-answer-commit\n")
    with pytest.raises(ValueError, match="history"):
        validate_data_container(workspace, dataset)
