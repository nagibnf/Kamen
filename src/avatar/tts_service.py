"""TTS gRPC service with pluggable backend (stub by default)."""
from __future__ import annotations

import argparse
import asyncio
from typing import Iterable, Tuple

import grpc

import avatar_pb2
import avatar_pb2_grpc
from avatar.config import build_effective_config, load_persona_config, load_stack_config


class TtsBackend:
    def synthesize(
        self, text: str, voice_profile_id: str | None, voice_sample_path: str | None
    ) -> Tuple[bytes, int]:
        raise NotImplementedError


class MockTtsBackend(TtsBackend):
    def synthesize(
        self, text: str, voice_profile_id: str | None, voice_sample_path: str | None
    ) -> Tuple[bytes, int]:
        sample_rate = 24000
        duration_s = max(0.2, min(1.0, len(text) / 50.0))
        samples = int(sample_rate * duration_s)
        silence = b"\x00\x00" * samples
        return silence, sample_rate


class Qwen3TtsBackend(TtsBackend):
    def __init__(self, model_name: str, device: str = "cuda") -> None:
        # Placeholder for real integration. The real package name may differ.
        try:
            import qwen3_tts  # type: ignore  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Qwen3-TTS backend not available. Install the Qwen3-TTS package."
            ) from exc
        self._model_name = model_name
        self._device = device

    def synthesize(
        self, text: str, voice_profile_id: str | None, voice_sample_path: str | None
    ) -> Tuple[bytes, int]:
        raise NotImplementedError("Qwen3-TTS integration pending")


class XttsBackend(TtsBackend):
    def __init__(self, model_name: str) -> None:
        try:
            from TTS.api import TTS  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Coqui TTS not available. Install with: pip install TTS") from exc
        self._tts = TTS(model_name)

    def synthesize(
        self, text: str, voice_profile_id: str | None, voice_sample_path: str | None
    ) -> Tuple[bytes, int]:
        if not voice_sample_path:
            raise RuntimeError("voice_sample_path required for XTTS voice cloning")
        wav = self._tts.tts(text=text, speaker_wav=voice_sample_path, language="pt")
        try:
            import numpy as np  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("numpy not available. Install with: pip install numpy") from exc
        pcm = (np.array(wav) * 32767.0).astype("int16").tobytes()
        return pcm, self._tts.synthesizer.output_sample_rate


class TtsService(avatar_pb2_grpc.TtsServiceServicer):
    def __init__(self, backend: TtsBackend, chunk_ms: int = 100) -> None:
        self._backend = backend
        self._chunk_ms = chunk_ms

    async def StreamTts(self, request, context):
        pcm, sample_rate = self._backend.synthesize(
            request.text,
            request.voice_profile_id or None,
            request.voice_sample_path or None,
        )
        if not pcm:
            return
        bytes_per_ms = int(sample_rate * 2 / 1000)
        chunk_size = bytes_per_ms * self._chunk_ms
        for i in range(0, len(pcm), chunk_size):
            yield avatar_pb2.AudioChunk(
                meta=request.meta,
                pcm_s16le=pcm[i : i + chunk_size],
                sample_rate=sample_rate,
                channels=1,
            )
            await asyncio.sleep(0.0)


def _build_backend(tts_cfg: dict) -> TtsBackend:
    backend = tts_cfg.get("backend", "mock")
    if backend == "qwen3_tts":
        return Qwen3TtsBackend(
            model_name=tts_cfg.get("model", "qwen3-tts-0.6b"),
            device=tts_cfg.get("device", "cuda"),
        )
    if backend == "xtts":
        return XttsBackend(model_name=tts_cfg.get("model", "tts_models/multilingual/xtts_v2"))
    return MockTtsBackend()


def _load_effective(stack_path: str, personas_dir: str, persona_id: str) -> dict:
    stack_cfg = load_stack_config(stack_path)
    persona_cfg = load_persona_config(persona_id, personas_dir)
    return build_effective_config(stack_cfg, persona_cfg)


async def serve(bind: str, port: int, backend: TtsBackend) -> None:
    server = grpc.aio.server()
    avatar_pb2_grpc.add_TtsServiceServicer_to_server(TtsService(backend), server)
    server.add_insecure_port(f"{bind}:{port}")
    await server.start()
    await server.wait_for_termination()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TTS gRPC service.")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=50053)
    parser.add_argument("--stack", default="/workspace/configs/stack/default.yaml")
    parser.add_argument("--personas-dir", default="/workspace/configs/personas")
    parser.add_argument("--persona-id", default="ana")
    args = parser.parse_args()

    effective = _load_effective(args.stack, args.personas_dir, args.persona_id)
    tts_cfg = effective.get("stack", {}).get("tts", {})
    backend = _build_backend(tts_cfg)
    asyncio.run(serve(args.bind, args.port, backend))


if __name__ == "__main__":
    main()
