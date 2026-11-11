"""Random selection uses public IDs only and leaves existing manifests untouched."""

import json
import random
from types import SimpleNamespace

import pytest

from scripts.studies import freeze_manifest as freeze
from scripts.studies import benchmark_matrix as matrix


def test_random_sample_reproduces_recorded_shuffle_without_questions(tmp_path, monkeypatch):
    tasks = [SimpleNamespace(id=f"public-{i}", query="private question") for i in range(104)]
    monkeypatch.setattr(freeze, "task_pools", lambda *a: {"kramabench": tasks})
    monkeypatch.setattr(matrix, "task_pools", lambda *a: {"kramabench": tasks})
    protocol = tmp_path / "protocol.json"
    protocol.write_text('{"effort":"max"}')
    original = tmp_path / "validation20.json"
    original.write_text('{"frozen":"unchanged"}')
    seed = 6820760213620092556
    args = ["--root", str(tmp_path), "--benchmarks", "kramabench", "--protocol-settings", str(protocol),
            "--sample-size", "20", "--sample-seed", str(seed)]
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    freeze.main([*args, "--output", str(first)])
    freeze.main([*args, "--output", str(second)])
    assert first.read_bytes() == second.read_bytes()
    manifest = json.loads(first.read_text())
    expected = list(tasks)
    random.Random(seed).shuffle(expected)
    assert manifest["kind"] == "matched-study-v1" and manifest["sampling"]["prior_scores_used"] is False
    assert len(manifest["sampling"]["population"]["kramabench"]) == 104
    assert [t.id for _, t in matrix.manifest_selections(tmp_path, manifest, 0, 20)] == [t.id for t in expected[:20]]
    assert "private question" not in first.read_text()
    assert original.read_text() == '{"frozen":"unchanged"}'
    with pytest.raises(ValueError, match="fresh output"):
        freeze.main([*args, "--output", str(first)])


@pytest.mark.parametrize("extra", [["--sample-size", "20"], ["--sample-seed", "1"]])
def test_partial_sampling_configuration_fails_before_loading_data(tmp_path, monkeypatch, extra):
    monkeypatch.setattr(freeze, "task_pools", lambda *a: pytest.fail("Invalid sampling read data"))
    with pytest.raises(ValueError, match="requires both"):
        freeze.main(["--root", str(tmp_path), "--benchmarks", "kramabench", "--protocol-settings", "unused",
                     "--output", str(tmp_path / "out.json"), *extra])


def test_full_manifest_default_still_preserves_all_upstream_tasks(tmp_path, monkeypatch):
    tasks = [SimpleNamespace(id=f"public-{i}", query="private question") for i in range(25)]
    monkeypatch.setattr(freeze, "task_pools", lambda *a: {"kramabench": tasks})
    protocol = tmp_path / "protocol.json"
    protocol.write_text("{}")
    output = tmp_path / "full.json"
    freeze.main(["--root", str(tmp_path), "--benchmarks", "kramabench", "--protocol-settings", str(protocol),
                 "--output", str(output)])
    manifest = json.loads(output.read_text())
    assert manifest["kind"] == "benchmark-full-v1" and "sampling" not in manifest
    assert [row["task_id"] for row in manifest["benchmarks"]["kramabench"]] == [t.id for t in tasks]
