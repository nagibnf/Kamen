"""VLM gRPC service with pluggable backend (stub by default)."""
from __future__ import annotations

import argparse
import asyncio
import io

import grpc

import avatar_pb2
import avatar_pb2_grpc
from avatar.config import build_effective_config, load_persona_config, load_stack_config


class VlmBackend:
    def analyze(self, frame: avatar_pb2.VideoFrame) -> avatar_pb2.VisionSummary:
        raise NotImplementedError


class MockVlmBackend(VlmBackend):
    def analyze(self, frame: avatar_pb2.VideoFrame) -> avatar_pb2.VisionSummary:
        return avatar_pb2.VisionSummary(
            meta=frame.meta,
            text="stub vision summary",
            tags=["stub"],
        )


class Qwen2VlBackend(VlmBackend):
    def __init__(self, model_name: str, device: str = "cuda", prompt: str = "") -> None:
        try:
            from transformers import AutoModelForVision2Seq, AutoProcessor  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "transformers not available. Install with: pip install transformers"
            ) from exc
        try:
            import torch  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("torch not available. Install with: pip install torch") from exc
        try:
            from PIL import Image  # type: ignore  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Pillow not available. Install with: pip install pillow") from exc

        self._processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
        torch_dtype = torch.float16 if device == "cuda" else torch.float32
        device_map = "auto" if device == "cuda" else None
        self._model = AutoModelForVision2Seq.from_pretrained(
            model_name,
            device_map=device_map,
            torch_dtype=torch_dtype,
            trust_remote_code=True,
        )
        if device_map is None:
            self._model.to(device)
        self._prompt = prompt or "Descreva a cena de forma breve em pt-BR."

    def _decode_image(self, frame: avatar_pb2.VideoFrame):
        from PIL import Image  # type: ignore

        if frame.format in ("jpeg", "jpg", "png"):
            return Image.open(io.BytesIO(frame.data)).convert("RGB")
        if frame.format == "rgb24":
            return Image.frombytes("RGB", (frame.width, frame.height), frame.data)
        raise RuntimeError(f"Unsupported image format: {frame.format}")

    def analyze(self, frame: avatar_pb2.VideoFrame) -> avatar_pb2.VisionSummary:
        image = self._decode_image(frame)
        inputs = self._processor(images=image, text=self._prompt, return_tensors="pt")
        inputs = inputs.to(self._model.device)
        outputs = self._model.generate(**inputs, max_new_tokens=64)
        text = self._processor.decode(outputs[0], skip_special_tokens=True)
        return avatar_pb2.VisionSummary(meta=frame.meta, text=text, tags=[])


class VlmService(avatar_pb2_grpc.VlmServiceServicer):
    def __init__(self, backend: VlmBackend) -> None:
        self._backend = backend

    async def AnalyzeFrame(self, request, context):
        return self._backend.analyze(request)


def _build_backend(vlm_cfg: dict) -> VlmBackend:
    backend = vlm_cfg.get("backend", "mock")
    if backend == "qwen2_vl":
        return Qwen2VlBackend(
            model_name=vlm_cfg.get("model", "qwen2-vl-2b"),
            device=vlm_cfg.get("device", "cuda"),
            prompt=vlm_cfg.get("prompt", ""),
        )
    return MockVlmBackend()


def _load_effective(stack_path: str, personas_dir: str, persona_id: str) -> dict:
    stack_cfg = load_stack_config(stack_path)
    persona_cfg = load_persona_config(persona_id, personas_dir)
    return build_effective_config(stack_cfg, persona_cfg)


async def serve(bind: str, port: int, backend: VlmBackend) -> None:
    server = grpc.aio.server()
    avatar_pb2_grpc.add_VlmServiceServicer_to_server(VlmService(backend), server)
    server.add_insecure_port(f"{bind}:{port}")
    await server.start()
    await server.wait_for_termination()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run VLM gRPC service.")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=50055)
    parser.add_argument("--stack", default="/workspace/configs/stack/default.yaml")
    parser.add_argument("--personas-dir", default="/workspace/configs/personas")
    parser.add_argument("--persona-id", default="ana")
    args = parser.parse_args()

    effective = _load_effective(args.stack, args.personas_dir, args.persona_id)
    vlm_cfg = effective.get("stack", {}).get("vlm", {})
    backend = _build_backend(vlm_cfg)
    asyncio.run(serve(args.bind, args.port, backend))


if __name__ == "__main__":
    main()
