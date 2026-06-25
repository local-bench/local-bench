from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

Json = Any
ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "suite" / "v1"


def main() -> None:
    items = _bfcl_items() + _fresh_items()
    out = SUITE / "tc_json_v1.jsonl"
    out.write_text(
        "".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for item in items
        ),
        encoding="utf-8",
    )
    (SUITE / "templates" / "tc_json_v1.txt").write_text(
        "\n".join(
            [
                "You are evaluating tool-calling conformance over plaintext JSON. You are given a JSON tool catalog and a user request. Decide which catalog tool calls are required.",
                "",
                "Tool catalog:",
                "{tool_catalog}",
                "",
                "User request:",
                "{user_request}",
                "",
                "Return exactly one JSON object and nothing else. Do not use markdown fences. Do not include prose. Use only tools from the catalog. Every call's arguments must match that tool's JSON Schema. The output schema is exactly:",
                '{"schema_version":"localbench.tc.v1","calls":[{"name":"tool.name","arguments":{}}]}',
                'Return {"schema_version":"localbench.tc.v1","calls":[]} if no tool is needed or no catalog tool can satisfy the request.',
                "",
            ]
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    _update_suite_json(len(items), digest)
    _update_lock(len(items), digest)
    print(f"{len(items)} {digest}")


def _bfcl_items() -> list[dict[str, Json]]:
    output: list[dict[str, Json]] = []
    for row in _load_jsonl(SUITE / "bfcl.jsonl"):
        functions = row["function"]
        answers = row["possible_answer"]
        calls = _gold_calls(answers, functions)
        category = str(row["category"])
        output.append(
            {
                "id": "tc-json-" + str(row["id"]),
                "source": "bfcl",
                "stratum": "bfcl_backbone",
                "prompt": _message_text(row["question"]),
                "tools": _bfcl_tools(functions, answers),
                "gold": {"order_matters": "parallel" not in category, "calls": calls},
                "match_policy": _policy(defaults=True),
            }
        )
    return output


def _fresh_items() -> list[dict[str, Json]]:
    calendar = _tool(
        "calendar.create_event",
        "Create a calendar event.",
        _obj(
            {
                "title": {"type": "string"},
                "date": {"type": "string"},
                "time": {"type": "string"},
                "duration_minutes": {"type": "integer"},
                "attendees": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            ["title", "date", "time", "duration_minutes"],
        ),
    )
    weather = _tool(
        "weather.get",
        "Get weather for a location.",
        _obj(
            {
                "location": {"type": "string"},
                "date": {"type": "string", "default": "today"},
                "units": {"type": "string", "enum": ["metric", "imperial"], "default": "metric"},
            },
            ["location"],
        ),
    )
    web = _tool("web.search", "Search the web.", _obj({"query": {"type": "string"}, "top_k": {"type": "integer", "default": 5}}, ["query"]))
    email = _tool(
        "email.send",
        "Send an email.",
        _obj(
            {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "cc": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            ["to", "subject", "body"],
        ),
    )
    unit = _tool("unit.convert", "Convert a quantity between units.", _obj({"value": {"type": "number"}, "from_unit": {"type": "string"}, "to_unit": {"type": "string"}}, ["value", "from_unit", "to_unit"]))
    timer = _tool("timer.set", "Set a countdown timer.", _obj({"duration_minutes": {"type": "integer"}, "label": {"type": "string"}}, ["duration_minutes", "label"]))
    task = _tool("todo.add", "Add a task to the todo list.", _obj({"title": {"type": "string"}, "priority": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"}}, ["title"]))
    maps = _tool("maps.route", "Plan a route.", _obj({"origin": {"type": "string"}, "destination": {"type": "string"}, "mode": {"type": "string", "enum": ["drive", "walk", "transit"], "default": "drive"}}, ["origin", "destination"]))
    notes = _tool("notes.create", "Create a note.", _obj({"title": {"type": "string"}, "body": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}, "default": []}}, ["title", "body"]))
    rows = [
        ("Schedule a design review on 2026-07-02 at 09:30 for 45 minutes with Ana and Bo.", [calendar, email], [_call("calendar.create_event", {"title": "design review", "date": "2026-07-02", "time": "09:30", "duration_minutes": 45, "attendees": ["ana@example.com", "bo@example.com"]})], True, {"/date": "iso_date", "/time": "hhmm_24h"}, ["/attendees"]),
        ("What is the weather in Brisbane tomorrow in Celsius?", [weather, web], [_call("weather.get", {"location": "Brisbane", "date": "tomorrow", "units": "metric"})], True, {}, []),
        ("Search the web for LocalBench tc_json benchmark notes; return 3 results.", [web, notes], [_call("web.search", {"query": "LocalBench tc_json benchmark notes", "top_k": 3})], True, {}, []),
        ("Email Sam that the draft is ready for review.", [email, calendar], [_call("email.send", {"to": "sam@example.com", "subject": "Draft ready for review", "body": "The draft is ready for review."})], True, {}, []),
        ("Convert 12.5 miles to kilometers.", [unit, weather], [_call("unit.convert", {"value": 12.5, "from_unit": "mile", "to_unit": "kilometer"})], True, {}, []),
        ("Set a 20 minute pasta timer.", [timer, task], [_call("timer.set", {"duration_minutes": 20, "label": "pasta"})], True, {}, []),
        ("Add a high priority todo to renew the SSL certificate.", [task, email], [_call("todo.add", {"title": "renew the SSL certificate", "priority": "high"})], True, {"/priority": "enum-casefold"}, []),
        ("Plan a walking route from Central Station to City Hall.", [maps, weather], [_call("maps.route", {"origin": "Central Station", "destination": "City Hall", "mode": "walk"})], True, {}, []),
        ("Create a note titled Ideas with tags bench and tools.", [notes, email], [_call("notes.create", {"title": "Ideas", "body": "", "tags": ["bench", "tools"]})], True, {}, ["/tags"]),
        ("Schedule lunch on 2026-08-10 at 12:00 for 60 minutes, then email Pat the invite is on the calendar.", [calendar, email], [_call("calendar.create_event", {"title": "lunch", "date": "2026-08-10", "time": "12:00", "duration_minutes": 60}), _call("email.send", {"to": "pat@example.com", "subject": "Lunch scheduled", "body": "The lunch invite is on the calendar."})], True, {"/date": "iso_date", "/time": "hhmm_24h"}, []),
        ("Check Tokyo weather and search for indoor activities there.", [weather, web], [_call("weather.get", {"location": "Tokyo"}), _call("web.search", {"query": "Tokyo indoor activities", "top_k": 5})], False, {}, []),
        ("Convert 100 USD to AUD and add a todo to check the receipt.", [unit, task], [_call("unit.convert", {"value": 100, "from_unit": "USD", "to_unit": "AUD"}), _call("todo.add", {"title": "check the receipt"})], True, {}, []),
        ("Tell me a short joke without using tools.", [web, email], [], True, {}, []),
        ("What is 18 plus 24? Do not use a tool.", [unit, web], [], True, {}, []),
        ("Summarize the phrase: reliable JSON beats clever prose.", [notes, email], [], True, {}, []),
        ("Open the garage door.", [weather, web, email], [], True, {}, []),
        ("Book a flight from BNE to MEL tomorrow morning.", [weather, calendar, email], [], True, {}, []),
        ("Turn off the kitchen lights.", [timer, task, web], [], True, {}, []),
        ("Email Lee and Morgan that standup moved to 10:15, and put standup on the calendar for 2026-09-03.", [email, calendar], [_call("email.send", {"to": "lee@example.com", "subject": "Standup moved", "body": "Standup moved to 10:15."}), _call("email.send", {"to": "morgan@example.com", "subject": "Standup moved", "body": "Standup moved to 10:15."}), _call("calendar.create_event", {"title": "standup", "date": "2026-09-03", "time": "10:15", "duration_minutes": 15})], True, {"/date": "iso_date", "/time": "hhmm_24h"}, []),
        ("Search for pytest parametrization examples and create a note with the query text.", [web, notes], [_call("web.search", {"query": "pytest parametrization examples"}), _call("notes.create", {"title": "pytest search", "body": "pytest parametrization examples"})], True, {}, []),
        ("Set a 5 minute tea timer and a 30 minute laundry timer.", [timer], [_call("timer.set", {"duration_minutes": 5, "label": "tea"}), _call("timer.set", {"duration_minutes": 30, "label": "laundry"})], False, {}, []),
        ("Weather for New York in Fahrenheit please.", [weather], [_call("weather.get", {"location": "New York", "units": "imperial"})], True, {"/units": "enum-casefold"}, []),
        ("Create event Demo Day on 2026-10-05T00:00:00 at 14:00:00 for 90 minutes.", [calendar], [_call("calendar.create_event", {"title": "Demo Day", "date": "2026-10-05", "time": "14:00", "duration_minutes": 90})], True, {"/date": "iso_date", "/time": "hhmm_24h"}, []),
        ("Send an email to ops@example.com with cc audit and finance about the Q3 export.", [email], [_call("email.send", {"to": "ops@example.com", "subject": "Q3 export", "body": "The Q3 export is ready.", "cc": ["audit@example.com", "finance@example.com"]})], True, {}, ["/cc"]),
        ("Convert 32 fahrenheit to celsius.", [unit], [_call("unit.convert", {"value": 32, "from_unit": "fahrenheit", "to_unit": "celsius"})], True, {}, []),
        ("Add a todo to file expenses; default priority is fine.", [task], [_call("todo.add", {"title": "file expenses"})], True, {}, []),
        ("Plan a route from Home to Airport using the default travel mode.", [maps], [_call("maps.route", {"origin": "Home", "destination": "Airport"})], True, {}, []),
        ("Search local weather radar and send Dana a note saying I am checking it.", [web, email], [_call("web.search", {"query": "local weather radar"}), _call("email.send", {"to": "dana@example.com", "subject": "Weather radar", "body": "I am checking it."})], True, {}, []),
        ("Create a note with tags alpha, beta, gamma in any order.", [notes], [_call("notes.create", {"title": "tag test", "body": "alpha beta gamma", "tags": ["alpha", "beta", "gamma"]})], True, {}, ["/tags"]),
        ("Schedule release checkpoint for 2026-11-12 at 16:45 and add a high priority todo to prepare release notes.", [calendar, task], [_call("calendar.create_event", {"title": "release checkpoint", "date": "2026-11-12", "time": "16:45", "duration_minutes": 30}), _call("todo.add", {"title": "prepare release notes", "priority": "high"})], True, {"/date": "iso_date", "/time": "hhmm_24h", "/priority": "enum-casefold"}, []),
    ]
    return [
        _fresh(index, prompt, tools, calls, order=order, normalizers=normalizers, unordered=unordered)
        for index, (prompt, tools, calls, order, normalizers, unordered) in enumerate(rows, start=1)
    ]


def _fresh(index: int, prompt: str, tools: list[dict[str, Json]], calls: list[dict[str, Json]], *, order: bool, normalizers: dict[str, str], unordered: list[str]) -> dict[str, Json]:
    return {
        "id": f"tc-json-fresh-{index:03d}",
        "source": "hand-authored",
        "stratum": "fresh_common_tools",
        "prompt": prompt,
        "tools": tools,
        "gold": {"order_matters": order, "calls": calls},
        "match_policy": _policy(normalizers=normalizers, unordered=unordered, defaults=True),
    }


def _load_jsonl(path: Path) -> list[dict[str, Json]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _message_text(question: Json) -> str:
    current = question[0] if isinstance(question, list) and len(question) == 1 and isinstance(question[0], list) else question
    if isinstance(current, str):
        return current
    if not isinstance(current, list):
        return ""
    return "\n".join(
        f"{item['role']}: {item['content']}"
        for item in current
        if isinstance(item, dict) and isinstance(item.get("role"), str) and isinstance(item.get("content"), str)
    )


def _bfcl_tools(functions: list[Json], answers: list[Json]) -> list[dict[str, Json]]:
    answer_by_name = {
        name: params
        for answer in answers
        if isinstance(answer, dict)
        for name, params in answer.items()
        if isinstance(name, str) and isinstance(params, dict)
    }
    output: list[dict[str, Json]] = []
    for function in functions:
        name = function["name"]
        output.append(
            _tool(
                name,
                function["description"],
                _json_schema(function["parameters"], answer_by_name.get(name, {}), None),
            )
        )
    return output


def _json_schema(schema: dict[str, Json], answers: dict[str, Json], answer_values: list[Json] | None) -> dict[str, Json]:
    type_map = {"dict": "object", "float": "number", "tuple": "array"}
    output: dict[str, Json] = {}
    schema_type = schema.get("type")
    if isinstance(schema_type, str) and schema_type != "any":
        output["type"] = type_map.get(schema_type, schema_type)
    answer_type = _answer_json_type(answer_values)
    if answer_type is not None and output.get("type") not in (None, answer_type):
        output["type"] = [output["type"], answer_type]
    if isinstance(schema.get("description"), str):
        output["description"] = schema["description"]
    properties = schema.get("properties")
    if isinstance(properties, dict):
        output["properties"] = {
            key: _json_schema(value, {}, answers.get(key) if isinstance(answers.get(key), list) else None)
            for key, value in properties.items()
            if isinstance(key, str) and isinstance(value, dict)
        }
        output["additionalProperties"] = False
    required = schema.get("required")
    if isinstance(required, list):
        output["required"] = [item for item in required if isinstance(item, str)]
    items = schema.get("items")
    if isinstance(items, dict):
        output["items"] = _json_schema(items, {}, None)
    elif output.get("type") == "array":
        output["items"] = {}
    if isinstance(output.get("properties"), dict):
        for key, values in answers.items():
            if isinstance(values, list) and "" in values and key in output["properties"]:
                default = _materialize_default(values)
                if default is not None:
                    output["properties"][key]["default"] = default
    return output


def _gold_calls(answers: list[Json], functions: list[Json]) -> list[dict[str, Json]]:
    required = _required_by_function(functions)
    output: list[dict[str, Json]] = []
    for answer in answers:
        name, params = next(iter(answer.items()))
        args = {
            key: _materialize_arg(values)
            for key, values in params.items()
            if isinstance(values, list) and (key in required.get(name, set()) or "" not in values)
        }
        output.append(_call(name, args))
    return output


def _required_by_function(functions: list[Json]) -> dict[str, set[str]]:
    output: dict[str, set[str]] = {}
    for function in functions:
        required = function.get("parameters", {}).get("required", [])
        output[function["name"]] = {item for item in required if isinstance(item, str)}
    return output


def _materialize_arg(values: list[Json]) -> Json:
    return _materialize_value(next(item for item in values if item != ""))


def _materialize_value(value: Json) -> Json:
    if isinstance(value, list):
        return [_materialize_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _materialize_arg(item) if isinstance(item, list) else _materialize_value(item)
            for key, item in value.items()
        }
    return value


def _materialize_default(values: list[Json]) -> Json | None:
    candidates = [value for value in values if value != ""]
    if not candidates:
        return None
    first = candidates[0]
    if isinstance(first, list) and not first:
        return None
    return _materialize_value(first)


def _answer_json_type(values: list[Json] | None) -> str | None:
    if values is None:
        return None
    candidates = [value for value in values if value != ""]
    if not candidates:
        return None
    value = _materialize_value(candidates[0])
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return None


def _tool(name: str, description: str, parameters: dict[str, Json]) -> dict[str, Json]:
    return {"name": name, "description": description, "parameters": parameters}


def _obj(properties: dict[str, Json], required: list[str]) -> dict[str, Json]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


def _call(name: str, arguments: dict[str, Json]) -> dict[str, Json]:
    return {"name": name, "arguments": arguments}


def _policy(*, normalizers: dict[str, str] | None = None, unordered: list[str] | None = None, defaults: bool) -> dict[str, Json]:
    return {
        "default": "typed_canonical_json_equality",
        "normalizers": normalizers or {},
        "allow_default_omission": defaults,
        "unordered_arrays": unordered or [],
    }


def _update_suite_json(count: int, digest: str) -> None:
    path = SUITE / "suite.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["benches"]["tc_json_v1"] = {
        "chance_correction_baseline": 0.0,
        "decoding": {"max_tokens": 16384, "temperature": 0},
        "itemsets": {"standard": {"file": "tc_json_v1.jsonl", "item_count": count, "sha256": digest}},
        "lane_caps": {},
        "template": "templates/tc_json_v1.txt",
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _update_lock(count: int, digest: str) -> None:
    path = SUITE / "itemsets.lock.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["files"]["tc_json_v1.jsonl"] = {
        "item_count": count,
        "sha256": digest,
        "source_dataset": "BFCL single-turn backbone plus hand-authored common-tool conformance items",
        "source_revision": "local suite/v1 tc_json_v1",
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
