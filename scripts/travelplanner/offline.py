#!/usr/bin/env python3
"""Five-arm integration check using scripted replies, never model performance."""
import argparse
from collections import Counter
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import socket
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fakes import ScriptedClient
from benchmarks.travelplanner.adapter import NativeSession, ROOT as BENCH, public_task, tasks, team_for
from harness.agent_team import AgentTeam
from harness.config import digest, source_digest
from harness.communication import FORMS
from harness.pool import bind_permissions
from harness.trace import Trace, read_trace, validate, usage_summary


def deny_network(*args, **kwargs):
    raise AssertionError("Offline integration test attempted network access")


def rows(native, name, **arguments):
    values, offset = [], 0
    while True:
        page = native.request("tool", name=name, arguments=dict(arguments, offset=offset, limit=50))
        if "rows" not in page:
            raise AssertionError(f"Fixture cannot use {name}: {page}")
        values.extend(page["rows"])
        offset = page["next_offset"]
        if offset is None:
            return values


def fixture(native, row):
    """Build a deterministic scorer fixture from real tools, NOT an agent solver.

    Test-only access to structured task fields never crosses the public prompt.
    It intentionally covers one easy validation task, not benchmark success rate.
    """
    city = row["dest"]
    outbound = min(rows(native, "flight_search", origin=row["org"], destination=city,
                        departure_date=row["date"][0]), key=lambda r: r["Price"])
    inbound = min(rows(native, "flight_search", origin=city, destination=row["org"],
                       departure_date=row["date"][-1]), key=lambda r: r["Price"])
    hotels = rows(native, "accommodation_search", city=city)
    hotel = min((r for r in hotels if r["minimum nights"] <= 2 and r["maximum occupancy"] >= row["people_number"]), key=lambda r: r["price"])
    meals = sorted(rows(native, "restaurant_search", city=city), key=lambda r: r["Average Cost"])[:9]
    attractions = rows(native, "attraction_search", city=city)[:3]
    plan = []
    for i in range(3):
        flight = outbound if i == 0 else inbound
        movement = f"from {flight['OriginCityName']} to {flight['DestCityName']}"
        transport = f"Flight Number: {flight['Flight Number']}, {movement}, Departure Time: {flight['DepTime']}, Arrival Time: {flight['ArrTime']}"
        plan.append(dict(day=i + 1, current_city=movement if i != 1 else city,
                         transportation=transport if i != 1 else "-",
                         breakfast=f"{meals[i * 3]['Name']}, {city}",
                         lunch=f"{meals[i * 3 + 1]['Name']}, {city}",
                         dinner=f"{meals[i * 3 + 2]['Name']}, {city}",
                         attraction=f"{attractions[i]['Name']}, {city};",
                         accommodation=f"{hotel['NAME']}, {city}" if i < 2 else "-"))
    return plan


def scripted_policy(row, plan):
    def policy(messages, tools, choice):
        if choice == "none":
            last = json.loads(messages[-1]["content"])
            # A deterministic encoder is sufficient to test transport plumbing.
            content = last["intent"]
            if "schema" in last["handoff_instruction"]:
                content = json.dumps(dict(conclusion=content, key_facts=[], ruled_out=[],
                                          open_questions=[], confidence="low"))
            return {"content": content}
        role = messages[0]["content"].split("Reusable role: ")[1].split(".")[0]
        count = sum(m["role"] == "assistant" for m in messages)
        if role == "researcher":
            if count == 0:
                return {"calls": [("flight_search", dict(origin=row["org"], destination=row["dest"], departure_date=row["date"][0]))]}
            if count == 1:
                return {"calls": [("flight_search", dict(origin=row["dest"], destination=row["org"], departure_date=row["date"][-1]))]}
            if count == 2:
                return {"calls": [("send_message", dict(recipient="constraint_analyst", content="Coordinate two lodging nights with these flights.", evidence_ids=["e1"]))]}
        elif role == "constraint_analyst" and count == 0:
            return {"calls": [("accommodation_search", dict(city=row["dest"]))]}
        elif role == "data_analyst" and count == 0:
            return {"calls": [("restaurant_search", dict(city=row["dest"])), ("attraction_search", dict(city=row["dest"]))]}
        elif role == "leader":
            initial = json.loads(messages[1]["content"])
            read_calls = [c for m in messages for c in m.get("tool_calls", []) if c["function"]["name"] in ("read_evidence", "request_evidence")]
            if initial["handoff_form"] in ("document_retrieval", "adaptive") and not read_calls:
                for message in messages:
                    if message["role"] != "user":
                        continue
                    try:
                        packet = json.loads(message["content"]).get("incoming_handoff", {})
                    except ValueError:
                        continue
                    if packet.get("evidence_ids"):
                        return {"calls": [("read_evidence", {"id": packet["evidence_ids"][0]})]}
            return {"content": json.dumps(plan)}
        return {"content": f"{role} completed its scripted tool checks; reconcile exact observations."}
    return policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # No environment loading, credentials, provider client or paid parser/judge.
    socket.create_connection = deny_network
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    args.output.mkdir(parents=True, exist_ok=False)
    selected = tasks()
    row = selected[0]
    request = public_task(row)
    spec = team_for(request)
    manifest = dict(kind="offline_fixture", paid_calls=0, source_digest=source_digest(),
                    driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    fixture_client_sha256=hashlib.sha256((ROOT / "tests/fakes.py").read_bytes()).hexdigest(),
                    python=sys.version, dependencies={name: version(name) for name in ("pandas", "numpy", "requests", "tqdm")},
                    prepared=digest(json.loads((BENCH / "assets/prepared.json").read_text())),
                    candidate_count=len(selected), levels=dict(Counter(t.get("level", "unknown") for t in selected)),
                    candidate_ids=[t["task_id"] for t in selected], tested_task=row["task_id"],
                    team=spec.payload(), forms=list(FORMS), headroom="unmeasured", semantic_loss="unmeasured")
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2))
    with NativeSession() as native:
        plan = fixture(native, row)
        positive = native.grade(row, json.dumps(plan))
        assert positive["native_correct"] and positive["audited_correct"], positive
        negative = native.grade(dict(row, budget=0), json.dumps(plan))
        assert negative["correct"] is False and negative["checks"]["hard"]["valid_cost"][0] is False
        (args.output / "scorer-fixtures.json").write_text(json.dumps(dict(positive=positive, negative=negative), indent=2))
        controls, results = set(), []
        tools = native.tools()
        permissions = bind_permissions(spec, {t.name: "search" for t in tools})
        for form in FORMS:
            path = args.output / "traces" / f"{form}.jsonl"
            with Trace(path, form) as trace:
                trace.emit("run_start", kind="offline_fixture", paid_calls=0)
                client = ScriptedClient(scripted_policy(row, plan))
                team = AgentTeam(spec, form, client, trace, tools, permissions)
                if controls:
                    assert team.control_digest in controls, "Control drift before inference"
                else:
                    (args.output / "control.json").write_text(json.dumps(team.control, indent=2))
                result = team.run_task(request)
                assert result["status"] == "completed", result
                grade = native.grade(row, result["final"])
                assert grade["audited_correct"]
                trace.emit("run_end", status=result["status"])
            events = read_trace(path)
            assert not validate(events), validate(events)
            assert any(e["type"] == "peer_delivery" and e["recipient"] == "constraint_analyst" and e["sender"] == "researcher" for e in events)
            controls.add(team.control_digest)
            usage = usage_summary(events)
            result.update(form=form, kind="offline_fixture", paid_calls=0, grade=grade, usage=usage,
                          usage_is_synthetic=True, semantic_loss=None,
                          tool_output_chars=sum(len(e["observation"]) for e in events if e["type"] == "tool_call"),
                          domain_schemas=team.control["domain_schemas"],
                          system_prompt_chars={n: len(a.messages[0]["content"]) for n, a in team.agents.items()})
            (args.output / f"{form}.json").write_text(json.dumps(result, indent=2))
            results.append({k: result[k] for k in ("form", "status", "calls", "tool_calls", "tool_output_chars")})
        assert len(controls) == 1
        summary = dict(paid_calls=0, control_digest=next(iter(controls)), results=results,
                       candidate_count=len(selected), headroom="unmeasured", semantic_loss="unmeasured",
                       conclusion="Integration contracts only; no model success, cache hit rate or causal loss evidence.")
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
