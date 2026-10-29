import json
from pathlib import Path

import pytest

from benchmarks.travelplanner.adapter import ROOT, NativeSession, public_task, tasks, team_for


def test_public_task_excludes_grading_fields():
    row = dict(query="Plan a trip", reference_information="SECRET_REFERENCE", local_constraint="SECRET_GRADING")
    public = public_task(row)
    assert "SECRET" not in public
    assert team_for(public).task_digest


def test_native_bridge_never_exposes_planner_or_grader():
    session = object.__new__(NativeSession)
    tools = session.tools()
    assert len(tools) == 5
    assert not {"planner", "grade", "notebook", "run_online"} & {t.name for t in tools}
    assert all(t.budgeted and not t.concurrent for t in tools)


@pytest.mark.skipif(not (ROOT / "assets/prepared.json").exists(), reason="Pinned native data not prepared")
def test_prepared_task_selection_and_native_tools():
    selected = tasks()
    assert selected and all(t["days"] == 3 and t["visiting_city_number"] == 1 for t in selected)
    assert all("reference_information" not in t for t in selected)
    row = selected[0]
    with NativeSession() as native:
        flights = native.request("tool", name="flight_search", arguments=dict(
            origin=row["org"], destination=row["dest"], departure_date=row["date"][0], limit=1))
        assert flights["total_rows"] >= 1 and len(flights["rows"]) == 1
        first = flights["rows"][0]
        assert first["OriginCityName"] == row["org"] and first["FlightDate"] == row["date"][0]
        assert native.grade(row, "not JSON")["correct"] is False
        assert native.grade(row, "[]")["correct"] is False


def test_native_failures_not_wrong_answers():
    session = object.__new__(NativeSession)
    session.errors = ["timeout"]
    assert session.grade({"days": 3}, "[]")["correct"] is None
