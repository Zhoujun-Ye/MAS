"""Read-only validation of externally provisioned data-processing containers."""

import hashlib
import json
from pathlib import Path
import subprocess


def overlaps(first, second):
    first, second = Path(first).resolve(), Path(second).resolve()
    return first.is_relative_to(second) or second.is_relative_to(first)


def validate_artifact_paths(dataset, output, archive=None, *, work_roots=()):
    """Check resolved paths before creating logs; read-only binds do not protect host writes."""
    visible = [dataset, *work_roots]
    for private in (output, archive):
        if private is not None and any(overlaps(private, root) for root in visible):
            raise ValueError("Evidence/output/archive paths must not overlap model-visible data or workspaces")


def validate_data_container(workspace, dataset, *, output=None):
    """Fail closed on accidental host/source/network exposure; never provision.

    This is a deployment guard, not a general security sandbox certification.
    The caller must use a trusted image without embedded credentials or answers.
    """
    dataset = Path(dataset).resolve(strict=True)
    if getattr(workspace, "outputs", {}):
        raise ValueError("A new session requires an empty retained-output namespace")
    if output is not None:
        validate_artifact_paths(dataset, output, getattr(workspace, "archive_dir", None))
    info = json.loads(subprocess.check_output(
        ["docker", "inspect", "--type", "container", workspace.container]))[0]
    host = info["HostConfig"]
    if (not info["State"]["Running"] or host["NetworkMode"] != "none" or host["Privileged"]
            or host.get("PidMode") == "host" or host.get("IpcMode") == "host"
            or host.get("CapAdd") or host.get("Devices")):
        raise ValueError("Require a running, nonprivileged, network-disabled data container")
    mounts = {entry["Destination"]: entry for entry in info["Mounts"]}
    if set(mounts) != {"/data", "/workspace"} or workspace.workdir != "/workspace":
        raise ValueError("Only /data and /workspace mounts are permitted")
    data, work = mounts["/data"], mounts["/workspace"]
    if (data["Type"] != "bind" or data["RW"] or Path(data["Source"]).resolve() != dataset
            or not work["RW"] or work["Type"] != "bind"):
        raise ValueError("Require the selected read-only dataset and a writable bind workspace")
    work_root = Path(work["Source"]).resolve(strict=True)
    validate_artifact_paths(dataset, output, getattr(workspace, "archive_dir", None), work_roots=(work_root,))
    if dataset.is_relative_to(work_root) or work_root.is_relative_to(dataset):
        raise ValueError("Input and output roots must be separate")
    if not (work_root / ".git").is_dir() or any(p.name != ".git" for p in work_root.iterdir()):
        raise ValueError("Each task needs a fresh, empty Git workspace")
    # An empty tree must not hide reference answers in reachable Git history.
    if subprocess.check_output(["git", "-C", str(work_root), "rev-list", "--all"]).strip():
        raise ValueError("Workspace Git history must also be empty")
    files = {}
    for path in sorted(dataset.rglob("*")):
        if path.is_symlink():
            raise ValueError("Dataset symlinks are not accepted")
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            files[str(path.relative_to(dataset))] = {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}
    if not files:
        raise ValueError("Dataset is empty")
    return {"image_id": info["Image"], "container_id": info.get("Id", workspace.container),
            "network": "none", "dataset_files": files,
            "resources": {key: host.get(key) for key in ("NanoCpus", "Memory", "PidsLimit", "ReadonlyRootfs")},
            "mounts": [{k: m[k] for k in ("Source", "Destination", "RW", "Type")}
                       for m in sorted(info["Mounts"], key=lambda m: m["Destination"])]}
