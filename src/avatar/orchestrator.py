"""Orchestrator CLI to test the end-to-end pipeline via gRPC."""
from __future__ import annotations

import argparse
import asyncio
import uuid
import wave
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import grpc

import avatar_pb2
import avatar_pb2_grpc
from avatar.config import build_effective_config, load_persona_config, load_stack_config


@dataclass
class ServiceEndpoints:
    asr: str
    llm: str
    tts: str
    lipsync: str
    vlm: str


def _make_meta(persona_id: str, session_id: str, request_id: str) -> avatar_pb2.Meta:
    return avatar_pb2.Meta(
        persona_id=persona_id,
        session_id=session_id,
        request_id=request_id,
    )


def _load_endpoints(stack_cfg: dict) -> ServiceEndpoints:
    services = stack_cfg.get("services", {})
    return ServiceEndpoints(
        asr=services.get("asr", "localhost:50051"),
        llm=services.get("llm", "localhost:50052"),
        tts=services.get("tts", "localhost:50053"),
        lipsync=services.get("lipsync", "localhost:50054"),
        vlm=services.get("vlm", "localhost:50055"),
    )


async def _stream_wav_as_audio(
    wav_path: str, meta: avatar_pb2.Meta, chunk_ms: int = 40
) -> AsyncIterator[avatar_pb2.AudioChunk]:
    with wave.open(wav_path, "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        if sampwidth != 2:
            raise RuntimeError("Only 16-bit PCM WAV supported")
        bytes_per_ms = int(sample_rate * channels * sampwidth / 1000)
        chunk_size = bytes_per_ms * chunk_ms
        while True:
            data = wf.readframes(int(chunk_size / (channels * sampwidth)))
            if not data:
                break
            yield avatar_pb2.AudioChunk(
                meta=meta,
                pcm_s16le=data,
                sample_rate=sample_rate,
                channels=channels,
            )


async def run_asr(asr_addr: str, wav_path: str, meta: avatar_pb2.Meta) -> str:
    async with grpc.aio.insecure_channel(asr_addr) as channel:
        stub = avatar_pb2_grpc.AsrServiceStub(channel)
        text = ""
        async for partial in stub.StreamAsr(_stream_wav_as_audio(wav_path, meta)):
            if partial.text:
                text = partial.text
            if partial.is_final:
                break
        return text


async def run_llm(
    llm_addr: str,
    text: str,
    meta: avatar_pb2.Meta,
    persona_profile: str,
    vision_summary: str = "",
    context: str = "",
) -> str:
    async with grpc.aio.insecure_channel(llm_addr) as channel:
        stub = avatar_pb2_grpc.LlmServiceStub(channel)
        request = avatar_pb2.LlmRequest(
            meta=meta,
            text=text,
            context=context,
            vision_summary=vision_summary,
            persona_profile=persona_profile,
        )
        tokens = []
        async for event in stub.StreamLlm(request):
            if event.HasField("token"):
                if event.token.token:
                    tokens.append(event.token.token)
            elif event.HasField("tool_call"):
                # Tool execution happens in the LLM service.
                pass
            elif event.HasField("tool_result"):
                pass
        return " ".join(tokens).strip()


async def run_tts(
    tts_addr: str,
    text: str,
    meta: avatar_pb2.Meta,
    voice_sample_path: Optional[str],
    out_wav: Optional[str],
) -> tuple[bytes, int]:
    async with grpc.aio.insecure_channel(tts_addr) as channel:
        stub = avatar_pb2_grpc.TtsServiceStub(channel)
        request = avatar_pb2.TtsRequest(
            meta=meta, text=text, voice_sample_path=voice_sample_path or ""
        )
        pcm = bytearray()
        sample_rate = 24000
        async for chunk in stub.StreamTts(request):
            pcm.extend(chunk.pcm_s16le)
            sample_rate = chunk.sample_rate or sample_rate

        if out_wav:
            with wave.open(out_wav, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(bytes(pcm))
        return bytes(pcm), sample_rate


async def run_lipsync(
    lipsync_addr: str,
    pcm: bytes,
    sample_rate: int,
    meta: avatar_pb2.Meta,
    out_video: Optional[str],
) -> None:
    async with grpc.aio.insecure_channel(lipsync_addr) as channel:
        stub = avatar_pb2_grpc.LipsyncServiceStub(channel)

        async def stream_audio() -> AsyncIterator[avatar_pb2.AudioChunk]:
            bytes_per_ms = int(sample_rate * 2 / 1000)
            chunk_size = bytes_per_ms * 40
            for i in range(0, len(pcm), chunk_size):
                yield avatar_pb2.AudioChunk(
                    meta=meta,
                    pcm_s16le=pcm[i : i + chunk_size],
                    sample_rate=sample_rate,
                    channels=1,
                )

        video_bytes = bytearray()
        async for frame in stub.StreamLipsync(stream_audio()):
            if frame.format in ("h264", "mp4"):
                video_bytes.extend(frame.data)
        if out_video:
            with open(out_video, "wb") as fh:
                fh.write(video_bytes)


def _load_effective(stack_path: str, personas_dir: str, persona_id: str) -> dict:
    stack_cfg = load_stack_config(stack_path)
    persona_cfg = load_persona_config(persona_id, personas_dir)
    return build_effective_config(stack_cfg, persona_cfg)


async def main_async(args) -> None:
    effective = _load_effective(args.stack, args.personas_dir, args.persona_id)
    endpoints = _load_endpoints(effective.get("stack", {}))

    session_id = args.session_id or str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    meta = _make_meta(args.persona_id, session_id, request_id)

    if args.text:
        user_text = args.text
    else:
        if not args.wav:
            raise RuntimeError("Provide --text or --wav")
        user_text = await run_asr(endpoints.asr, args.wav, meta)

    persona = effective.get("persona", {})
    reply = await run_llm(
        endpoints.llm,
        user_text,
        meta,
        persona_profile=persona.get("system_prompt", ""),
    )
    pcm, sample_rate = await run_tts(
        endpoints.tts,
        reply,
        meta,
        voice_sample_path=persona.get("voice_sample"),
        out_wav=args.out_wav,
    )

    if args.out_video:
        await run_lipsync(endpoints.lipsync, pcm, sample_rate, meta, args.out_video)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run end-to-end pipeline test.")
    parser.add_argument("--stack", default="/workspace/configs/stack/default.yaml")
    parser.add_argument("--personas-dir", default="/workspace/configs/personas")
    parser.add_argument("--persona-id", default="ana")
    parser.add_argument("--wav", help="Input WAV (16-bit PCM)")
    parser.add_argument("--text", help="Bypass ASR and use text input")
    parser.add_argument("--out-wav", help="Output WAV path")
    parser.add_argument("--out-video", help="Output H264 path")
    parser.add_argument("--session-id", help="Optional session id")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
