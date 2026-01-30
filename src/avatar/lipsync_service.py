"""Lipsync gRPC service (Wav2Lip placeholder)."""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import tempfile
import wave

import grpc

import avatar_pb2
import avatar_pb2_grpc
from avatar.config import build_effective_config, load_persona_config, load_stack_config


def _now_ms() -> int:
    return int(time.time() * 1000)


class LipsyncBackend:
    async def run(self, audio_stream, meta: avatar_pb2.Meta):
        raise NotImplementedError


class MockLipsyncBackend(LipsyncBackend):
    async def run(self, audio_stream, meta: avatar_pb2.Meta):
        # Consume audio stream and emit a single empty frame.
        async for _chunk in audio_stream:
            break
        yield avatar_pb2.VideoFrame(
            meta=meta,
            data=b"",
            width=256,
            height=256,
            format="h264",
        )


class Wav2LipBackend(LipsyncBackend):
    def __init__(self, repo_path: str, checkpoint: str, base_video: str, fps: int = 30) -> None:
        self._repo_path = repo_path
        self._checkpoint = checkpoint
        self._base_video = base_video
        self._fps = fps

    async def run(self, audio_stream, meta: avatar_pb2.Meta):
        pcm = bytearray()
        sample_rate = 24000
        async for chunk in audio_stream:
            pcm.extend(chunk.pcm_s16le)
            sample_rate = chunk.sample_rate or sample_rate

        if not pcm:
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = os.path.join(tmpdir, "audio.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(bytes(pcm))

            out_path = os.path.join(tmpdir, "out.mp4")
            cmd = [
                "python",
                os.path.join(self._repo_path, "inference.py"),
                "--checkpoint_path",
                self._checkpoint,
                "--face",
                self._base_video,
                "--audio",
                wav_path,
                "--outfile",
                out_path,
                "--fps",
                str(self._fps),
            ]
            subprocess.run(cmd, check=True)
            with open(out_path, "rb") as fh:
                data = fh.read()

        yield avatar_pb2.VideoFrame(
            meta=meta,
            data=data,
            width=0,
            height=0,
            format="mp4",
        )


class LipsyncService(avatar_pb2_grpc.LipsyncServiceServicer):
    def __init__(self, backend: LipsyncBackend) -> None:
        self._backend = backend

    async def StreamLipsync(self, request_iterator, context):
        first_meta = avatar_pb2.Meta(ts_ms=_now_ms())
        async for chunk in request_iterator:
            if chunk.meta:
                first_meta = chunk.meta
            # Use a small wrapper that re-yields this chunk as the stream.
            async def stream():
                yield chunk
                async for rest in request_iterator:
                    yield rest

            async for frame in self._backend.run(stream(), first_meta):
                yield frame
            return


def _build_backend(lipsync_cfg: dict, persona: dict) -> LipsyncBackend:
    backend = lipsync_cfg.get("backend", "mock")
    if backend == "wav2lip":
        repo_path = lipsync_cfg.get("repo_path")
        checkpoint = lipsync_cfg.get("model", "wav2lip_gan.pth")
        base_video = persona.get("base_video")
        if not repo_path or not base_video:
            raise RuntimeError("wav2lip requires repo_path and persona.base_video")
        return Wav2LipBackend(
            repo_path=repo_path,
            checkpoint=checkpoint,
            base_video=base_video,
            fps=int(lipsync_cfg.get("fps", 30)),
        )
    return MockLipsyncBackend()


def _load_effective(stack_path: str, personas_dir: str, persona_id: str) -> dict:
    stack_cfg = load_stack_config(stack_path)
    persona_cfg = load_persona_config(persona_id, personas_dir)
    return build_effective_config(stack_cfg, persona_cfg)


async def serve(bind: str, port: int, backend: LipsyncBackend) -> None:
    server = grpc.aio.server()
    avatar_pb2_grpc.add_LipsyncServiceServicer_to_server(LipsyncService(backend), server)
    server.add_insecure_port(f"{bind}:{port}")
    await server.start()
    await server.wait_for_termination()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Lipsync gRPC service.")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=50054)
    parser.add_argument("--stack", default="/workspace/configs/stack/default.yaml")
    parser.add_argument("--personas-dir", default="/workspace/configs/personas")
    parser.add_argument("--persona-id", default="ana")
    args = parser.parse_args()

    effective = _load_effective(args.stack, args.personas_dir, args.persona_id)
    lipsync_cfg = effective.get("stack", {}).get("lipsync", {})
    persona = effective.get("persona", {})
    backend = _build_backend(lipsync_cfg, persona)
    asyncio.run(serve(args.bind, args.port, backend))


if __name__ == "__main__":
    main()
