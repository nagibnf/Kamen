"""LLM gRPC service (pluggable backend with tool-call support)."""
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


class LlmBackend:
    def generate(self, text: str, context: str, vision_summary: str, persona_profile: str) -> str:
        raise NotImplementedError


class MockBackend(LlmBackend):
    def generate(self, text: str, context: str, vision_summary: str, persona_profile: str) -> str:
        return text or "ok"


class TransformersBackend(LlmBackend):
    def __init__(self, model_name: str, device: str = "cuda", max_tokens: int = 256) -> None:
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "transformers not available. Install with: pip install transformers"
            ) from exc
        self._tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        self._model = AutoModelForCausalLM.from_pretrained(
            model_name, device_map=device, trust_remote_code=True
        )
        self._max_tokens = max_tokens

    def generate(self, text: str, context: str, vision_summary: str, persona_profile: str) -> str:
        prompt = f"{persona_profile}\n{context}\n{vision_summary}\nUser: {text}\nAssistant:"
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)
        outputs = self._model.generate(
            **inputs, max_new_tokens=self._max_tokens, do_sample=True, temperature=0.7
        )
        full = self._tokenizer.decode(outputs[0], skip_special_tokens=True)
        if "Assistant:" in full:
            return full.split("Assistant:", 1)[-1].strip()
        return full.strip()


class TensorRtBackend(LlmBackend):
    def __init__(self, model_name: str) -> None:
        # Placeholder for TensorRT-LLM integration.
        self._model_name = model_name

    def generate(self, text: str, context: str, vision_summary: str, persona_profile: str) -> str:
        raise NotImplementedError("TensorRT-LLM integration pending")


class LlmService(avatar_pb2_grpc.LlmServiceServicer):
    def __init__(self, backend: LlmBackend, tools_enabled: bool, allowlist: Iterable[str]) -> None:
        self._backend = backend
        self._tools_enabled = tools_enabled
        self._allowlist = list(allowlist)
        self._registry = default_registry()

    async def StreamLlm(self, request, context):
        response_text = self._backend.generate(
            request.text, request.context, request.vision_summary, request.persona_profile
        )
        tool_call = _parse_tool_call(response_text)
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

        tokens = response_text.split() or ["ok"]
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


async def serve(
    bind: str, port: int, backend: LlmBackend, tools_enabled: bool, allowlist: Iterable[str]
) -> None:
    server = grpc.aio.server()
    avatar_pb2_grpc.add_LlmServiceServicer_to_server(
        LlmService(backend=backend, tools_enabled=tools_enabled, allowlist=allowlist), server
    )
    server.add_insecure_port(f"{bind}:{port}")
    await server.start()
    await server.wait_for_termination()


def _build_backend(llm_cfg: dict) -> LlmBackend:
    backend = llm_cfg.get("backend", "mock")
    if backend == "transformers":
        return TransformersBackend(
            model_name=llm_cfg.get("model", "Qwen/Qwen2.5-7B-Instruct"),
            device=llm_cfg.get("device", "cuda"),
            max_tokens=int(llm_cfg.get("max_tokens", 256)),
        )
    if backend == "tensorrt_llm":
        return TensorRtBackend(model_name=llm_cfg.get("model", "qwen2.5-7b"))
    return MockBackend()


def _load_effective(stack_path: str, personas_dir: str, persona_id: str) -> dict:
    stack_cfg = load_stack_config(stack_path)
    persona_cfg = load_persona_config(persona_id, personas_dir)
    return build_effective_config(stack_cfg, persona_cfg)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM gRPC service (stub).")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=50052)
    parser.add_argument("--stack", default="/workspace/configs/stack/default.yaml")
    parser.add_argument("--personas-dir", default="/workspace/configs/personas")
    parser.add_argument("--persona-id", default="ana")
    args = parser.parse_args()

    effective = _load_effective(args.stack, args.personas_dir, args.persona_id)
    llm_cfg = effective.get("stack", {}).get("llm", {})
    tools_cfg = effective.get("stack", {}).get("tools", {})
    backend = _build_backend(llm_cfg)
    asyncio.run(
        serve(
            args.bind,
            args.port,
            backend=backend,
            tools_enabled=bool(tools_cfg.get("enabled", False)),
            allowlist=tools_cfg.get("allowlist", []),
        )
    )


if __name__ == "__main__":
    main()
