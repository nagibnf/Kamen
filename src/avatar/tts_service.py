"""TTS gRPC service with pluggable backend (stub by default)."""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import tempfile
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
    """Invoke Qwen3-TTS via external command template.

    Expected template variables:
    - {text}, {out_wav}, {voice_sample}
    """

    def __init__(self, cmd_template: str) -> None:
        self._cmd_template = cmd_template

    def synthesize(
        self, text: str, voice_profile_id: str | None, voice_sample_path: str | None
    ) -> Tuple[bytes, int]:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_wav = os.path.join(tmpdir, "out.wav")
            cmd = self._cmd_template.format(
                text=text,
                out_wav=out_wav,
                voice_sample=voice_sample_path or "",
            )
            subprocess.run(cmd, shell=True, check=True)
            with open(out_wav, "rb") as fh:
                data = fh.read()
        # Assume 24k by default (can be adjusted by config).
        return data, 24000


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
    def __init__(
        self,
        backend: TtsBackend,
        chunk_ms: int = 100,
        default_voice_sample_path: str | None = None,
    ) -> None:
        self._backend = backend
        self._chunk_ms = chunk_ms
        self._default_voice_sample_path = default_voice_sample_path

    async def StreamTts(self, request, context):
        voice_sample_path = request.voice_sample_path or self._default_voice_sample_path
        pcm, sample_rate = self._backend.synthesize(
            request.text,
            request.voice_profile_id or None,
            voice_sample_path,
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
        cmd_template = tts_cfg.get("cmd_template")
        if not cmd_template:
            raise RuntimeError("qwen3_tts requires cmd_template in config")
        return Qwen3TtsBackend(cmd_template=cmd_template)
    if backend == "xtts":
        return XttsBackend(model_name=tts_cfg.get("model", "tts_models/multilingual/xtts_v2"))
    return MockTtsBackend()


def _load_effective(stack_path: str, personas_dir: str, persona_id: str) -> dict:
    stack_cfg = load_stack_config(stack_path)
    persona_cfg = load_persona_config(persona_id, personas_dir)
    return build_effective_config(stack_cfg, persona_cfg)


async def serve(
    bind: str, port: int, backend: TtsBackend, default_voice_sample_path: str | None
) -> None:
    server = grpc.aio.server()
    avatar_pb2_grpc.add_TtsServiceServicer_to_server(
        TtsService(backend, default_voice_sample_path=default_voice_sample_path), server
    )
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
    persona = effective.get("persona", {})
    backend = _build_backend(tts_cfg)
    asyncio.run(
        serve(
            args.bind,
            args.port,
            backend,
            default_voice_sample_path=persona.get("voice_sample"),
        )
    )


if __name__ == "__main__":
    main()
