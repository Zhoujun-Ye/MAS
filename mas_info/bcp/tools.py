"""The official search and get_document tools: same descriptions and output format."""

from __future__ import annotations

import json

from ..agent import Observation, Tool


def search_tool(retriever, k: int, truncate) -> Tool:
    def run(args: dict, agent) -> Observation:
        hits = retriever.search(str(args["query"]), k)
        results = [
            {"docid": hit["docid"], "score": hit["score"], "snippet": truncate(hit["text"])}
            for hit in hits
        ]
        return Observation(json.dumps(results, indent=2), {"docids": [hit["docid"] for hit in hits]})

    return Tool(
        "search",
        f"Perform a search on a knowledge source. Returns top-{k} hits with docid, score, "
        "and snippet. The snippet contains the document's contents (may be truncated based "
        "on token limits).",
        {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query string"}},
            "required": ["query"],
        },
        run,
        budgeted=True,
    )


def get_document_tool(retriever) -> Tool:
    def run(args: dict, agent) -> Observation:
        docid = str(args["docid"])
        doc = retriever.get_document(docid)
        if doc is None:
            return Observation(
                json.dumps({"error": f"Document with docid '{docid}' not found"}), {"docids": []}
            )
        return Observation(json.dumps(doc, indent=2), {"docids": [docid], "fetched": True})

    return Tool(
        "get_document",
        "Retrieve a full document by its docid.",
        {
            "type": "object",
            "properties": {"docid": {"type": "string", "description": "Document ID to retrieve"}},
            "required": ["docid"],
        },
        run,
        budgeted=True,
    )


def artifact_label(tool_name: str):
    """Index label of a stored output in C4: the request, never the content."""
    if tool_name == "search":
        return lambda args: f"query={json.dumps(str(args.get('query', '')), ensure_ascii=False)}"
    return lambda args: f"docid={args.get('docid')}"
