"""Mock gRPC services for early end-to-end testing.

These stubs allow the pipeline to run without heavy models.
Replace with real implementations per service when ready.
"""
from __future__ import annotations

import argparse
import asyncio
import time

import grpc

import avatar_pb2
import avatar_pb2_grpc


def _now_ms() -> int:
    return int(time.time() * 1000)


class AsrService(avatar_pb2_grpc.AsrServiceServicer):
    async def StreamAsr(self, request_iterator, context):
        last_meta = None
        async for chunk in request_iterator:
            last_meta = chunk.meta
            if chunk.pcm_s16le:
                yield avatar_pb2.AsrPartial(
                    meta=chunk.meta,
                    text="stub asr partial",
                    is_final=False,
                    start_ms=0,
                    end_ms=0,
                    confidence=0.5,
                )
        if last_meta is not None:
            yield avatar_pb2.AsrPartial(
                meta=last_meta,
                text="stub asr final",
                is_final=True,
                start_ms=0,
                end_ms=0,
                confidence=0.5,
            )


class LlmService(avatar_pb2_grpc.LlmServiceServicer):
    async def StreamLlm(self, request, context):
        tokens = request.text.split() or ["ok"]
        for token in tokens:
            yield avatar_pb2.LlmToken(
                meta=request.meta,
                token=token,
                is_final=False,
                latency_ms=0,
            )
            await asyncio.sleep(0.01)
        yield avatar_pb2.LlmToken(
            meta=request.meta,
            token="",
            is_final=True,
            latency_ms=0,
        )


class TtsService(avatar_pb2_grpc.TtsServiceServicer):
    async def StreamTts(self, request, context):
        sample_rate = 24000
        duration_s = 0.2
        samples = int(sample_rate * duration_s)
        silence = b"\x00\x00" * samples
        yield avatar_pb2.AudioChunk(
            meta=request.meta,
            pcm_s16le=silence,
            sample_rate=sample_rate,
            channels=1,
        )


class LipsyncService(avatar_pb2_grpc.LipsyncServiceServicer):
    async def StreamLipsync(self, request_iterator, context):
        meta = None
        async for chunk in request_iterator:
            meta = chunk.meta
            break
        if meta is None:
            meta = avatar_pb2.Meta(ts_ms=_now_ms())
        yield avatar_pb2.VideoFrame(
            meta=meta,
            data=b"",
            width=256,
            height=256,
            format="h264",
        )


class VlmService(avatar_pb2_grpc.VlmServiceServicer):
    async def AnalyzeFrame(self, request, context):
        return avatar_pb2.VisionSummary(
            meta=request.meta,
            text="stub vision summary",
            tags=["stub"],
        )


async def serve(bind: str, port: int) -> None:
    server = grpc.aio.server()
    avatar_pb2_grpc.add_AsrServiceServicer_to_server(AsrService(), server)
    avatar_pb2_grpc.add_LlmServiceServicer_to_server(LlmService(), server)
    avatar_pb2_grpc.add_TtsServiceServicer_to_server(TtsService(), server)
    avatar_pb2_grpc.add_LipsyncServiceServicer_to_server(LipsyncService(), server)
    avatar_pb2_grpc.add_VlmServiceServicer_to_server(VlmService(), server)

    server.add_insecure_port(f"{bind}:{port}")
    await server.start()
    await server.wait_for_termination()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run mock gRPC services.")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=50051)
    args = parser.parse_args()
    asyncio.run(serve(args.bind, args.port))


if __name__ == "__main__":
    main()
