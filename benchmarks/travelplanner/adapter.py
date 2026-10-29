"""Public task boundary, native tool bridge and direct-JSON scoring."""
import ast
import csv
import json
import os
from pathlib import Path
import select
import subprocess
import sys

from harness.agent import Observation, Tool
from harness.pool import select_team

ROOT = Path(__file__).resolve().parent
FIELDS = ("current_city", "transportation", "breakfast", "lunch", "dinner", "attraction", "accommodation")
OUTPUT = """Return only a JSON array, one object per day in chronological order.
Each object has day (integer starting at 1), current_city, transportation,
breakfast, lunch, dinner, attraction, accommodation (all other fields strings).
Use 'from CITY to CITY' for travel days, otherwise the city name. Use exact
database entity names followed by ', City'; separate attractions with ';' and
include a trailing ';'. Flights use 'Flight Number: ID, from CITY to CITY,
Departure Time: HH:MM, Arrival Time: HH:MM'. Missing items use '-'."""


def tasks(path=ROOT / "assets/validation.csv"):
    """Selection is based on published horizon, never on outcome or reference plans."""
    selected = []
    with Path(path).open(newline="") as source:
        for index, row in enumerate(csv.DictReader(source)):
            for key in ("days", "visiting_city_number", "people_number", "budget"):
                row[key] = int(row[key])
            for key in ("date", "local_constraint"):
                row[key] = ast.literal_eval(row[key])
            if row["days"] == 3 and row["visiting_city_number"] == 1:
                row.pop("reference_information", None)
                row["task_id"] = f"validation-{index}"
                selected.append(row)
    return selected


def public_task(row):
    # Do not expose structured grading fields or sole-planning reference answers.
    return row["query"] + "\n\n" + OUTPUT


def team_for(request):
    return select_team(request, {
        "researcher": "Find feasible outbound and return transport. Share dates, identifiers, timing and total transport cost with the constraint analyst and leader.",
        "constraint_analyst": "Find feasible lodging. Coordinate with the researcher on total budget and dates; preserve minimum nights, occupancy and restrictions. Report feasibility to the leader.",
        "data_analyst": "Find non-repeated meals and attractions matching the complete request. Compare costs and constraints, and report exact names and cities to the leader.",
        "leader": "Coordinate and reconcile transport, lodging, meals and attractions. Verify joint constraints and produce the required final JSON itinerary.",
    }, selector="travelplanner-short-rule-v1")


class NativeError(RuntimeError):
    pass


class NativeSession:
    """One isolated process, no provider credentials, no network or LLM planner.

    Native imports change cwd and hold large dataframes. Keeping them in this
    process prevents cwd/module pollution in the harness. Not a code sandbox.
    """
    def __init__(self, root=ROOT, timeout=120):
        self.timeout = timeout
        self.errors = []
        env = {"PATH": os.defpath, "PYTHONHASHSEED": "0", "PYTHONUNBUFFERED": "1"}
        self.proc = subprocess.Popen([sys.executable, str(ROOT / "native_worker.py"), str(Path(root).resolve())],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, env=env)
        try:
            self._receive()
        except BaseException:
            self.close()
            raise

    def _receive(self):
        if not select.select([self.proc.stdout], [], [], self.timeout)[0]:
            self.proc.kill()
            self.proc.wait()
            raise NativeError("Native backend timeout")
        line = self.proc.stdout.readline()
        if not line:
            raise NativeError("Native backend exited without a response")
        reply = json.loads(line)
        if "error" in reply:
            raise NativeError(reply["error"])
        return reply["result"]

    def request(self, operation, **kwargs):
        try:
            self.proc.stdin.write(json.dumps(dict(operation=operation, **kwargs)) + "\n")
            self.proc.stdin.flush()
            return self._receive()
        except Exception as error:
            self.errors.append(str(error))
            raise NativeError(str(error)) from error

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.proc.stdin.close()
        self.proc.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def tools(self):
        result = []
        definitions = {
            "flight_search": ("Find flights on an exact date.", ("origin", "destination", "departure_date")),
            "accommodation_search": ("Find lodging including prices, minimum nights, occupancy and house rules.", ("city",)),
            "restaurant_search": ("Find restaurants including cuisines and average costs.", ("city",)),
            "attraction_search": ("Find attractions in a city.", ("city",)),
            "distance_search": ("Read offline road distance, duration and cost; never calls online maps.", ("origin", "destination", "mode")),
        }
        for name, (description, fields) in definitions.items():
            properties = {f: {"type": "string"} for f in fields}
            if name == "distance_search":
                properties["mode"]["enum"] = ["self-driving", "taxi"]
            # Pagination preserves full rows and explicit counts; no hidden top-k.
            properties["offset"] = {"type": "integer", "minimum": 0}
            properties["limit"] = {"type": "integer", "minimum": 1, "maximum": 50}

            def run(args, agent, name=name, fields=fields):
                if (not isinstance(args, dict) or not set(fields) <= args.keys()
                        or any(not isinstance(args[f], str) for f in fields)
                        or set(args) - set(fields) - {"offset", "limit"}):
                    return Observation("Invalid search arguments.", {"error": True})
                if name == "distance_search" and args["mode"] not in ("self-driving", "taxi"):
                    return Observation("Invalid transport mode.", {"error": True})
                offset, limit = args.get("offset", 0), args.get("limit", 20)
                if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50:
                    return Observation("Invalid pagination.", {"error": True})
                value = self.request("tool", name=name, arguments=args)
                return Observation(json.dumps(value, ensure_ascii=False), {"native_tool": True})
            result.append(Tool(name, description, {"type": "object", "properties": properties,
                          "required": list(fields), "additionalProperties": False}, run, budgeted=True))
        return result

    def grade(self, row, text):
        if self.errors:
            return dict(status="ungraded", correct=None, reason="environment_error", errors=self.errors[:])
        try:
            plan = json.loads(text)
        except (ValueError, TypeError):
            return dict(status="graded", correct=False, reason="invalid_json")
        if (not isinstance(plan, list) or len(plan) != row["days"]
                or any(not isinstance(day, dict) or any(not isinstance(day.get(k), str) for k in FIELDS)
                       or type(day.get("day")) is not int or day["day"] != i + 1 for i, day in enumerate(plan))):
            return dict(status="graded", correct=False, reason="invalid_plan_shape")
        try:
            return self.request("grade", task=row, plan=plan)
        except NativeError as error:
            return dict(status="ungraded", correct=None, reason="native_evaluator_error", detail=str(error))
