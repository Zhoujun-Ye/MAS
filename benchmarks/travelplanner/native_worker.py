"""Pinned native code bridge. Stdin protocol is private to the adapter, not a tool."""
import ast
from contextlib import redirect_stdout
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import socket
import sys
import types


def no_network(*args, **kwargs):
    raise RuntimeError("Network disabled in the offline native backend")


def load(root):
    manifest = json.loads((root / "assets/prepared.json").read_text())
    # Refuse drift before importing executable upstream code or loading its data.
    for entry in manifest["files"]:
        path = root / entry["path"]
        h = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                h.update(chunk)
        if h.hexdigest() != entry["sha256"]:
            raise ValueError(f"Prepared input changed: {entry['path']}")
    upstream = root / "upstream"
    sys.path.insert(0, str(upstream))
    # Import only the three pure native helpers required by the scorer/tools.
    # The untouched original file also imports an unused Gradio annotation UI.
    tree = ast.parse((upstream / "utils/func.py").read_text())
    names = {"get_valid_name_city", "extract_before_parenthesis", "extract_numbers_from_filenames"}
    tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in tree.body} != names:
        raise ValueError("Native helper contract changed")
    module = types.ModuleType("utils.func")
    module.__dict__.update(re=re, os=os)
    exec(compile(tree, str(upstream / "utils/func.py"), "exec"), module.__dict__)
    sys.modules["utils.func"] = module
    os.chdir(upstream / "evaluation")
    commonsense = importlib.import_module("evaluation.commonsense_constraint")
    hard = importlib.import_module("evaluation.hard_constraint")
    return commonsense, hard


def respond(request, common, hard):
    if request["operation"] == "tool":
        bindings = {"flight_search": common.flight, "accommodation_search": common.accommodation,
                    "restaurant_search": common.restaurants, "attraction_search": common.attractions,
                    "distance_search": common.googleDistanceMatrix}
        args = dict(request["arguments"])
        offset, limit = args.pop("offset", 0), args.pop("limit", 20)
        value = bindings[request["name"]].run(**args)
        if isinstance(value, str):
            return dict(text=value)
        page = value.iloc[offset:offset + limit]
        return dict(total_rows=len(value), offset=offset, next_offset=offset + len(page) if offset + len(page) < len(value) else None,
                    rows=json.loads(page.to_json(orient="records")))
    if request["operation"] == "grade":
        task, plan = request["task"], request["plan"]
        checks = dict(commonsense=common.evaluation(task, plan), hard=hard.evaluation(task, plan))
        checks = hard.convert_bool_values(checks)
        native_pass = all(value[0] is not False for group in checks.values() for value in group.values())
        # Native 3-day scoring does not enforce the requested destination or
        # flight date. Keep these independent audit checks, not silent changes.
        destination = True
        for day in plan:
            location = day["current_city"]
            places = common.extract_from_to(location) if location.startswith("from ") else (location,)
            if not places or task["dest"] not in places:
                destination = False
        flight_dates = True
        for i, day in enumerate(plan):
            text = day["transportation"]
            if "flight" in text.lower():
                match = re.search(r"Flight Number: ([^,]+)", text)
                if not match:
                    flight_dates = False
                    continue
                rows = common.flight.data
                found = rows[(rows["Flight Number"] == match[1]) & (rows["FlightDate"] == task["date"][i])]
                if found.empty:
                    flight_dates = False
        audit = dict(requested_destination=destination, flight_dates=flight_dates)
        return dict(status="graded", correct=native_pass, native_correct=native_pass,
                    audited_correct=native_pass and all(audit.values()), checks=checks, audit=audit,
                    total_cost=float(hard.get_total_cost(task, plan)))
    raise ValueError("Unsupported private operation")


def main():
    socket.create_connection = no_network
    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    try:
        with redirect_stdout(sys.stderr):
            common, hard = load(Path(sys.argv[1]))
        print(json.dumps({"result": "ready"}), flush=True)
    except Exception as error:
        print(json.dumps({"error": f"{type(error).__name__}: {error}"}), flush=True)
        return
    for line in sys.stdin:
        try:
            with redirect_stdout(sys.stderr):
                result = respond(json.loads(line), common, hard)
            print(json.dumps({"result": result}), flush=True)
        except Exception as error:
            print(json.dumps({"error": f"{type(error).__name__}: {error}"}), flush=True)


if __name__ == "__main__":
    main()
