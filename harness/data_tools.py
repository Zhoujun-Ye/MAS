"""Bounded, non-executing inspection tools for an existing data container.

No model-supplied Python or shell is evaluated by these readers. Arbitrary code
execution, when granted separately, still relies on the container boundary.
"""

import json
import shlex

from .agent import Observation, Tool


INSPECT_SCRIPT = r'''
import json, os, sys
from pathlib import Path

request = json.load(sys.stdin)
root = Path(request.pop("root")).resolve(strict=True)
requested = request.get("path", ".")
if request["operation"] == "list" and requested == "/":
    requested = "."
path = (root / requested).resolve(strict=True)
if not path.is_relative_to(root):
    raise ValueError("Path must remain within the selected root")
if request["operation"] == "list":
    entries = []
    for entry in sorted(path.iterdir(), key=lambda p: p.name):
        # Do not expose entries whose targets are outside the granted root.
        if entry.is_symlink() or entry.name == ".git":
            continue
        entries.append({"path": str(entry.relative_to(root)),
                        "kind": "directory" if entry.is_dir() else "file",
                        "bytes": entry.stat().st_size if entry.is_file() else None})
    offset, limit = request.get("offset", 0), request.get("limit", 100)
    result = {"entries": entries[offset:offset+limit], "total": len(entries),
              "next_offset": min(offset+limit, len(entries))}
else:
    suffix = path.suffix.lower()
    limit = request.get("limit", 8000)
    if suffix == ".xlsx":
        import openpyxl
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = book[request.get("sheet") or book.sheetnames[0]]
            count = request.get("limit", 10)
            if count > 100:
                raise ValueError("XLSX limit is a row count and must be at most 100")
            offset = min(request.get("offset", 0), sheet.max_row)
            column_offset = min(request.get("column_offset", 0), sheet.max_column)
            column_end = min(column_offset + request.get("column_limit", 50), sheet.max_column)
            rows = list(sheet.iter_rows(min_row=offset + 1, max_row=min(offset + count, sheet.max_row),
                min_col=column_offset + 1, max_col=column_end, values_only=True)) if (
                    offset < sheet.max_row and column_offset < sheet.max_column) else []
            result = {"sheets": book.sheetnames, "sheet": sheet.title, "sample_rows": rows,
                      "row_offset": offset, "next_offset": offset + len(rows), "total_rows": sheet.max_row,
                      "column_offset": column_offset, "next_column_offset": column_end,
                      "total_columns": sheet.max_column,
                      "note": "Zero-based row/column offsets; cached formula values only, not recalculated."}
        finally:
            book.close()
    elif suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        page = request.get("page", 0)
        result = {"pages": len(reader.pages), "page": page,
                  "text": reader.pages[page].extract_text()[:limit]}
    else:
        offset = request.get("offset", 0)
        with path.open("rb") as stream:
            stream.seek(offset)
            data = stream.read(limit)
        result = {"text": data.decode("utf-8", errors="replace"),
                  "next_offset": offset + len(data), "bytes": path.stat().st_size,
                  "note": "Byte-range text preview; binary formats require an authorized analyst."}
encoded = json.dumps(result, ensure_ascii=True, default=str)
if len(encoded.encode()) > 24000:
    # Keep a valid, bounded response rather than returning truncated JSON.
    encoded = json.dumps({"error": "Preview too large; reduce limit/column_limit or inspect with an analyst."})
print(encoded)
'''


def inspection_tools(workspace, *, data_root="/data", work_root="/workspace"):
    """Stable schemas; runtime paths never enter the tool descriptions."""
    roots = {"data": data_root, "work": work_root}

    def invoke(operation, args, agent):
        payload = dict(args, root=roots[args["area"]], operation=operation)
        payload.pop("area")
        options = {}
        if getattr(agent, "session_budget", None) is not None:
            agent.session_budget.check()
            options["timeout"] = min(workspace.timeout, agent.session_budget.remaining_seconds())
        result = workspace.execute("python3 -I -c " + shlex.quote(INSPECT_SCRIPT),
                                   json.dumps(payload), **options)
        try:
            preview_error = bool(json.loads(result["output"]).get("error"))
        except (ValueError, AttributeError):
            preview_error = False
        return Observation(result["output"], {
            "error": bool(result.get("execution_error") or result["exit_code"] or result["truncated"] or preview_error),
            "error_kind": result.get("error_kind") or
                ("inspection_error" if result["exit_code"] or result["truncated"] or preview_error else None),
        })

    common = {"area": {"type": "string", "enum": ["data", "work"]},
              "path": {"type": "string", "minLength": 1},
              "offset": {"type": "integer", "minimum": 0}}
    return [
        Tool("list_files", "List one directory of data or work, sorted and paginated. Paths are relative to that area; omit path or use '.' for its root. '/' also selects the area root.",
             {"type": "object", "properties": dict(common, limit={"type": "integer", "minimum": 1, "maximum": 200}),
              "required": ["area"], "additionalProperties": False},
             lambda args, agent: invoke("list", args, agent), budgeted=True, read_only=True),
        Tool("inspect_file", "Read text (offset/limit in bytes), XLSX (zero-based row offset, limit up to 100 rows; default 10), or a PDF page. XLSX column_offset/column_limit select a column window; default 50 columns. Returns paging offsets and sheet names. No code execution; installed readers required.",
             {"type": "object", "properties": dict(common, limit={"type": "integer", "minimum": 1, "maximum": 8000},
                 column_offset={"type": "integer", "minimum": 0},
                 column_limit={"type": "integer", "minimum": 1, "maximum": 50},
                 sheet={"type": "string"}, page={"type": "integer", "minimum": 0}),
              "required": ["area", "path"], "additionalProperties": False},
             lambda args, agent: invoke("preview", args, agent), budgeted=True, read_only=True),
    ]
