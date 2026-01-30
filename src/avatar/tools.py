"""Tool registry for LLM function calls."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable


ToolFunc = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    func: ToolFunc


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def list(self) -> Dict[str, Tool]:
        return dict(self._tools)

    def allowed(self, allowlist: Iterable[str]) -> Dict[str, Tool]:
        allowed = {}
        for name in allowlist:
            tool = self._tools.get(name)
            if tool:
                allowed[name] = tool
        return allowed

    def execute(self, name: str, args: Dict[str, Any], allowlist: Iterable[str]) -> Dict[str, Any]:
        allowed = self.allowed(allowlist)
        tool = allowed.get(name)
        if tool is None:
            return {"ok": False, "error": f"tool_not_allowed: {name}"}
        try:
            return {"ok": True, "result": tool.func(args)}
        except Exception as exc:  # noqa: BLE001 - return structured error
            return {"ok": False, "error": str(exc)}


def _tool_get_time(_: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {"utc_time": now}


def _tool_list_personas(args: Dict[str, Any]) -> Dict[str, Any]:
    base_dir = Path(args.get("personas_dir", "/data/personas"))
    if not base_dir.exists():
        return {"personas": []}
    personas = sorted(p.name for p in base_dir.iterdir() if p.is_dir())
    return {"personas": personas}


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="get_time",
            description="Return current UTC time.",
            func=_tool_get_time,
        )
    )
    registry.register(
        Tool(
            name="list_personas",
            description="List available persona directories.",
            func=_tool_list_personas,
        )
    )
    return registry
