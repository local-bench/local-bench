from __future__ import annotations

import json
from pathlib import Path

from localbench._types import ChatMessage
from localbench.check.live_http import render_live_prompt
from localbench.check.live_sources import load_smoke_items
from localbench.checkset.input_runs import read_jsonl


class _RecordingRenderer:
    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []

    def render(self, messages: list[ChatMessage]) -> str:
        self.messages = messages
        return messages[-1]["content"]


def test_tool_gate_renders_lookup_schema_through_cli_owned_prompt_path() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    items = load_smoke_items(repo_root, repo_root / "checkset" / "check-set-v1.manifest.json")
    tool_gates = [
        item
        for item in items
        if item.module == "sanity-gates"
        and isinstance(item.source.get("expected"), dict)
        and isinstance(item.source["expected"].get("tool"), str)
    ]
    renderer = _RecordingRenderer()
    assert [item.item_id for item in tool_gates] == ["gate-determinism-tool"]

    rendered = render_live_prompt(tool_gates[0].module, tool_gates[0].source, renderer)

    assert '"name":"lookup"' in rendered
    assert '"id":{"type":"string"}' in rendered
    assert renderer.messages[0]["content"].startswith("Return canonical JSON only:")


def test_every_tc_json_item_renders_its_complete_tool_array() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    rows = read_jsonl(repo_root / "suite" / "v2" / "tc_json_v1.jsonl")
    renderer = _RecordingRenderer()

    for row in rows:
        rendered = render_live_prompt("tools-single", row, renderer)
        tools = row.get("tools")
        assert isinstance(tools, list) and tools
        assert json.dumps(tools, ensure_ascii=False, sort_keys=True, separators=(",", ":")) in rendered

    assert len(rows) == 330
