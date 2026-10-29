"""Transmission-loss diagnostics for BrowseComp-Plus (guide §5.2).

Validation may use gold labels: these measure how large the problem is; the
later detector must not depend on them.

- R_sys: share of evidence documents that some agent read (search hit or fetch).
- R_arrive: share of evidence documents whose content reached the decider: it
  read them itself, an upward report cites the docid, the full relay (C3)
  carried them verbatim, or it opened an artifact containing them (C4). The
  judge-based check of the guide (key facts present without citation) is a
  later, separate pass.
- L = (R_sys - R_arrive) / R_sys: share of read evidence that did not arrive.
- Answer arrival: the normalized gold answer string appears in what an agent
  received (task, boundary and tool messages). Short answers can match by
  accident, and derived answers never appear verbatim; a screening signal only.
"""

from __future__ import annotations

import re

from ..trace import contexts


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _mentions(text: str, docids: set[str]) -> set[str]:
    """Docids written as standalone tokens ([20], "docid": "20"), not inside ids like o20."""
    return {docid for docid in docids if re.search(rf"(?<!\w){re.escape(docid)}(?!\w)", text or "")}


def _received_text(messages: list[dict]) -> str:
    """What reached the agent (task, boundary and tool messages), not what it wrote."""
    return "\n".join(str(m.get("content") or "") for m in messages if m["role"] in ("user", "tool"))


def _shares(labelled: list[str], read: set[str], arrived: set[str]) -> dict:
    relevant = set(labelled)
    if not relevant:
        return {"n": 0, "r_sys": None, "r_arrive": None, "loss": None}
    read_rel, arrived_rel = relevant & read, relevant & arrived & read
    r_sys, r_arrive = len(read_rel) / len(relevant), len(arrived_rel) / len(relevant)
    return {
        "n": len(relevant),
        "read": sorted(read_rel),
        "arrived": sorted(arrived_rel),
        "r_sys": r_sys,
        "r_arrive": r_arrive,
        "loss": (r_sys - r_arrive) / r_sys if r_sys else None,
    }


def _duplicates(requests: list[tuple[str, str]]) -> dict:
    """Repeated requests overall and those repeating another agent's earlier request."""
    first_by: dict[str, set[str]] = {}
    repeated = cross_agent = 0
    for agent, key in requests:
        owners = first_by.setdefault(key, set())
        if owners:
            repeated += 1
            if owners - {agent}:
                cross_agent += 1
        owners.add(agent)
    total = len(requests)
    return {
        "total": total,
        "repeated": repeated,
        "cross_agent": cross_agent,
        "cross_agent_rate": cross_agent / total if total else None,
    }


def analyze(events: list[dict], task: dict, evidence: list[str], gold: list[str]) -> dict:
    final = next(event for event in events if event["type"] == "final")
    decider = final["agent"]
    seen: dict[str, set[str]] = {}
    searches, fetches = [], []
    for event in events:
        if event["type"] != "tool_call" or event["tool"] not in ("search", "get_document"):
            continue
        seen.setdefault(event["agent"], set()).update(event.get("docids", []))
        args = event.get("args") or {}
        if event["tool"] == "search":
            searches.append((event["agent"], _norm(str(args.get("query", "")))))
        else:
            fetches.append((event["agent"], str(args.get("docid", ""))))
    read = set().union(*seen.values()) if seen else set()
    arrived = set(seen.get(decider, set()))
    for event in events:
        if event["type"] == "boundary_msg" and event["direction"] == "up":
            text = event["content"] if event["relay"] == "full" else event["report"]
            arrived |= _mentions(text, read)
        elif event["type"] == "tool_call" and event["agent"] == decider and event["tool"] == "read_artifact":
            arrived |= _mentions(event["observation"], read)
    answer = _norm(task["answer"])
    answer_in = {
        agent: bool(answer) and answer in _norm(_received_text(messages))
        for agent, messages in contexts(events).items()
    }
    return {
        "decider": decider,
        "agents": sorted(answer_in),
        "evidence": _shares(evidence, read, arrived),
        "gold": _shares(gold, read, arrived),
        "answer_in_decider": answer_in.get(decider, False),
        "answer_in_other": any(found for agent, found in answer_in.items() if agent != decider),
        "answer_chars": len(answer),
        "searches": _duplicates(searches),
        "fetches": _duplicates(fetches),
    }


def failure_category(diagnosis: dict, correct: bool | None) -> str | None:
    """Guide §5.2 decomposition of a wrong answer: retrieval, transmission or synthesis.

    Rule-based first pass: the needed information is the gold answer string or
    the evidence documents. Judge labels (appendix B) refine it later.
    """
    if correct is not False:
        return None
    if diagnosis["answer_in_decider"]:
        return "synthesis"
    if diagnosis["answer_in_other"] or (diagnosis["evidence"]["loss"] or 0) > 0:
        return "transmission"
    return "retrieval"
