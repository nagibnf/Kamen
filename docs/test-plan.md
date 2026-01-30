# Plano de testes e benchmarks

## Objetivo
Validar latencia, FPS e qualidade do pipeline completo.

## Tipos de teste
1) **Unitario**: validacao de API e formatos (pcm/h264).
2) **Integracao**: ASR -> LLM -> TTS -> Lipsync.
   - usar `avatar.orchestrator` com WAV/texto
3) **Performance**: FPS e latencia E2E.
4) **Stress**: 2+ personas (fase 2).

## Metricas chave
- FPS (media e p95)
- Latencia E2E (p50/p95)
- TTFT (LLM)
- RTF ASR e TTS
- Uso de GPU/CPU
- MOS subjetivo (TTS)

## Cenarios base
1) Baseline (VLM off)
2) VLM on (1-2 FPS)
3) Voice cloning (Qwen3-TTS vs XTTS-v2)
4) Multi-persona (fase 2)
5) Tool calling (latencia e estabilidade)

## Criterios de sucesso
- Video >= 25 FPS (p95)
- Latencia E2E <= 2.0 s (p95)
- TTFT <= 600 ms (p95)

## Registro de resultados
Salvar CSV com:
- timestamp, stage, latency_ms, fps, gpu_util, mem
