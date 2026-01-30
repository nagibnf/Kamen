"""ASR gRPC service with optional faster-whisper backend."""
from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional

import grpc

import avatar_pb2
import avatar_pb2_grpc
from avatar.config import build_effective_config, load_persona_config, load_stack_config


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class Segment:
    text: str
    start_ms: int
    end_ms: int
    confidence: float


class AsrBackend:
    def transcribe(self, pcm_s16le: bytes, sample_rate: int) -> List[Segment]:
        raise NotImplementedError


class MockAsrBackend(AsrBackend):
    def transcribe(self, pcm_s16le: bytes, sample_rate: int) -> List[Segment]:
        return [Segment(text="stub asr", start_ms=0, end_ms=0, confidence=0.5)]


class FasterWhisperBackend(AsrBackend):
    def __init__(self, model_name: str, device: str, compute_type: str, language: str = "pt"):
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "faster-whisper not available. Install with: pip install faster-whisper"
            ) from exc
        self._model = WhisperModel(model_name, device=device, compute_type=compute_type)
        self._language = language

    def transcribe(self, pcm_s16le: bytes, sample_rate: int) -> List[Segment]:
        try:
            import numpy as np  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("numpy not available. Install with: pip install numpy") from exc

        if not pcm_s16le:
            return []
        audio = np.frombuffer(pcm_s16le, dtype=np.int16).astype("float32") / 32768.0
        segments, _info = self._model.transcribe(
            audio, language=self._language, vad_filter=False
        )
        results: List[Segment] = []
        for seg in segments:
            results.append(
                Segment(
                    text=seg.text.strip(),
                    start_ms=int(seg.start * 1000),
                    end_ms=int(seg.end * 1000),
                    confidence=0.5,
                )
            )
        return results


class AsrService(avatar_pb2_grpc.AsrServiceServicer):
    def __init__(self, backend: AsrBackend, partial_ms: int = 800) -> None:
        self._backend = backend
        self._partial_ms = partial_ms

    async def StreamAsr(self, request_iterator, context):
        buffer = bytearray()
        sample_rate: Optional[int] = None
        channels = 1
        last_emit = 0

        async for chunk in request_iterator:
            if sample_rate is None:
                sample_rate = chunk.sample_rate or 16000
                channels = chunk.channels or 1
            if channels != 1:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "only mono supported")
            buffer.extend(chunk.pcm_s16le)

            if sample_rate:
                bytes_per_ms = int(sample_rate * 2 / 1000)
                min_bytes = bytes_per_ms * self._partial_ms
                if len(buffer) >= min_bytes and (_now_ms() - last_emit) >= self._partial_ms:
                    last_emit = _now_ms()
                    segments = self._backend.transcribe(bytes(buffer), sample_rate)
                    text = " ".join(seg.text for seg in segments if seg.text)
                    if text:
                        yield avatar_pb2.AsrPartial(
                            meta=chunk.meta,
                            text=text,
                            is_final=False,
                            start_ms=segments[0].start_ms if segments else 0,
                            end_ms=segments[-1].end_ms if segments else 0,
                            confidence=segments[-1].confidence if segments else 0.0,
                        )

        if sample_rate and buffer:
            segments = self._backend.transcribe(bytes(buffer), sample_rate)
            text = " ".join(seg.text for seg in segments if seg.text)
            yield avatar_pb2.AsrPartial(
                meta=avatar_pb2.Meta(ts_ms=_now_ms()),
                text=text,
                is_final=True,
                start_ms=segments[0].start_ms if segments else 0,
                end_ms=segments[-1].end_ms if segments else 0,
                confidence=segments[-1].confidence if segments else 0.0,
            )


def _build_backend(asr_cfg: dict) -> AsrBackend:
    backend = asr_cfg.get("backend", "mock")
    if backend == "faster_whisper":
        return FasterWhisperBackend(
            model_name=asr_cfg.get("model", "distil-large-v3"),
            device=asr_cfg.get("device", "cuda"),
            compute_type=asr_cfg.get("compute_type", "int8_float16"),
            language=asr_cfg.get("language", "pt"),
        )
    return MockAsrBackend()


def _load_effective(stack_path: str, personas_dir: str, persona_id: str) -> dict:
    stack_cfg = load_stack_config(stack_path)
    persona_cfg = load_persona_config(persona_id, personas_dir)
    return build_effective_config(stack_cfg, persona_cfg)


async def serve(bind: str, port: int, backend: AsrBackend, partial_ms: int) -> None:
    server = grpc.aio.server()
    avatar_pb2_grpc.add_AsrServiceServicer_to_server(AsrService(backend, partial_ms), server)
    server.add_insecure_port(f"{bind}:{port}")
    await server.start()
    await server.wait_for_termination()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ASR gRPC service.")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--stack", default="/workspace/configs/stack/default.yaml")
    parser.add_argument("--personas-dir", default="/workspace/configs/personas")
    parser.add_argument("--persona-id", default="ana")
    args = parser.parse_args()

    effective = _load_effective(args.stack, args.personas_dir, args.persona_id)
    asr_cfg = effective.get("stack", {}).get("asr", {})
    backend = _build_backend(asr_cfg)
    partial_ms = int(asr_cfg.get("partial_ms", 800))
    asyncio.run(serve(args.bind, args.port, backend, partial_ms))


if __name__ == "__main__":
    main()
