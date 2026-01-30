"""LLM gRPC service (stub backend with tool-call support)."""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from typing import Iterable

import grpc

import avatar_pb2
import avatar_pb2_grpc
from avatar.config import build_effective_config, load_persona_config, load_stack_config
from avatar.tools import default_registry


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_tool_call(text: str) -> tuple[str, dict] | None:
    """Parse tool call format: 'tool:<name> <json_args>'."""
    if not text.startswith("tool:"):
        return None
    payload = text[len("tool:") :].strip()
    if not payload:
        return None
    parts = payload.split(" ", 1)
    name = parts[0].strip()
    args = {}
    if len(parts) > 1:
        try:
            args = json.loads(parts[1].strip())
        except json.JSONDecodeError:
            args = {"_raw": parts[1].strip()}
    return name, args


class LlmService(avatar_pb2_grpc.LlmServiceServicer):
    def __init__(self, tools_enabled: bool, allowlist: Iterable[str]) -> None:
        self._tools_enabled = tools_enabled
        self._allowlist = list(allowlist)
        self._registry = default_registry()

    async def StreamLlm(self, request, context):
        tool_call = _parse_tool_call(request.text)
        if self._tools_enabled and tool_call is not None:
            name, args = tool_call
            call = avatar_pb2.ToolCall(
                meta=request.meta,
                name=name,
                args_json=json.dumps(args),
            )
            yield avatar_pb2.LlmEvent(tool_call=call)
            result = self._registry.execute(name, args, self._allowlist)
            tool_result = avatar_pb2.ToolResult(
                meta=request.meta,
                name=name,
                result_json=json.dumps(result.get("result", {})),
                ok=bool(result.get("ok")),
                error=result.get("error", ""),
            )
            yield avatar_pb2.LlmEvent(tool_result=tool_result)
            yield avatar_pb2.LlmEvent(
                token=avatar_pb2.LlmToken(
                    meta=request.meta,
                    token="",
                    is_final=True,
                    latency_ms=0,
                )
            )
            return

        tokens = request.text.split() or ["ok"]
        start_ms = _now_ms()
        for token in tokens:
            yield avatar_pb2.LlmEvent(
                token=avatar_pb2.LlmToken(
                    meta=request.meta,
                    token=token,
                    is_final=False,
                    latency_ms=_now_ms() - start_ms,
                )
            )
            await asyncio.sleep(0.01)
        yield avatar_pb2.LlmEvent(
            token=avatar_pb2.LlmToken(
                meta=request.meta,
                token="",
                is_final=True,
                latency_ms=_now_ms() - start_ms,
            )
        )


async def serve(bind: str, port: int, tools_enabled: bool, allowlist: Iterable[str]) -> None:
    server = grpc.aio.server()
    avatar_pb2_grpc.add_LlmServiceServicer_to_server(
        LlmService(tools_enabled=tools_enabled, allowlist=allowlist), server
    )
    server.add_insecure_port(f"{bind}:{port}")
    await server.start()
    await server.wait_for_termination()


def _load_allowlist(stack_path: str, personas_dir: str, persona_id: str) -> tuple[bool, list]:
    stack_cfg = load_stack_config(stack_path)
    persona_cfg = load_persona_config(persona_id, personas_dir)
    effective = build_effective_config(stack_cfg, persona_cfg)
    tools_cfg = effective.get("stack", {}).get("tools", {})
    return bool(tools_cfg.get("enabled", False)), tools_cfg.get("allowlist", [])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM gRPC service (stub).")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=50052)
    parser.add_argument("--stack", default="/workspace/configs/stack/default.yaml")
    parser.add_argument("--personas-dir", default="/workspace/configs/personas")
    parser.add_argument("--persona-id", default="ana")
    args = parser.parse_args()

    tools_enabled, allowlist = _load_allowlist(args.stack, args.personas_dir, args.persona_id)
    asyncio.run(serve(args.bind, args.port, tools_enabled, allowlist))


if __name__ == "__main__":
    main()
