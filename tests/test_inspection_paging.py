import io
import json
import sys
from types import SimpleNamespace

import pytest

from harness.data_tools import INSPECT_SCRIPT, inspection_tools


def inspect_xlsx(tmp_path, monkeypatch, **options):
    (tmp_path / "table.xlsx").touch()
    selected = []

    def rows(**kwargs):
        selected.append(kwargs)
        return ((f"r{r}c{c}" for c in range(kwargs["min_col"], kwargs["max_col"] + 1))
                for r in range(kwargs["min_row"], kwargs["max_row"] + 1))

    # Openpyxl returns tuple rows, not generators.
    def iter_rows(**kwargs):
        return (tuple(row) for row in rows(**kwargs))

    class Book:
        sheetnames = ["Sheet1"]
        closed = False

        def __getitem__(self, name):
            assert name == "Sheet1"
            return SimpleNamespace(title=name, max_row=25, max_column=60, iter_rows=iter_rows)

        def close(self):
            self.closed = True

    book = Book()
    monkeypatch.setitem(sys.modules, "openpyxl", SimpleNamespace(load_workbook=lambda *a, **k: book))
    payload = {"root": str(tmp_path), "path": "table.xlsx", "operation": "preview", **options}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output)
    exec(compile(INSPECT_SCRIPT, "inspection", "exec"), {})
    assert book.closed
    return json.loads(output.getvalue()), selected


def test_xlsx_pages_rows_and_columns_instead_of_repeating_first_ten(tmp_path, monkeypatch):
    first, _ = inspect_xlsx(tmp_path, monkeypatch)
    assert first["sample_rows"][0][0] == "r1c1" and first["next_offset"] == 10
    second, selected = inspect_xlsx(tmp_path, monkeypatch, offset=10, limit=5, column_offset=50, column_limit=10)
    assert second["sample_rows"][0] == [f"r11c{c}" for c in range(51, 61)]
    assert second["next_offset"] == 15 and second["next_column_offset"] == 60
    assert second["total_rows"] == 25 and second["total_columns"] == 60
    assert selected[0]["values_only"] is True


def test_xlsx_tail_and_eof_are_explicit(tmp_path, monkeypatch):
    tail, _ = inspect_xlsx(tmp_path, monkeypatch, offset=23, limit=10)
    assert len(tail["sample_rows"]) == 2 and tail["next_offset"] == 25
    eof, selected = inspect_xlsx(tmp_path, monkeypatch, offset=25)
    assert eof["sample_rows"] == [] and eof["next_offset"] == 25 and selected == []
    with pytest.raises(ValueError, match="at most 100"):
        inspect_xlsx(tmp_path, monkeypatch, limit=101)


def test_oversize_preview_is_a_tool_error():
    workspace = SimpleNamespace(execute=lambda *a, **k: {
        "output": '{"error": "Preview too large"}', "exit_code": 0, "truncated": False})
    tool = next(t for t in inspection_tools(workspace) if t.name == "inspect_file")
    result = tool.run({"area": "data", "path": "table.xlsx"}, None)
    assert result.meta["error"] and result.meta["error_kind"] == "inspection_error"
    assert tool.read_only
